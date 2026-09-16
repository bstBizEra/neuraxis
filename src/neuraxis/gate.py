"""The Governance Gate.

Synchronous and blocking by construction (ILR-001 section 2.3). It is invoked
by the Execution, Learning and Evolution loops and returns a verdict; it has no
clock of its own and never resolves provisionally.

Evaluation order mirrors the spec's chain:

    Intent -> Identity -> Role -> Authority -> Scope -> Risk
        -> Evidence Requirement -> Decision

Every failure path yields a non-ALLOW verdict. There is no path through this
module that raises past the caller: an internal fault becomes DENY, because a
gate that crashes open is not a gate.
"""

from __future__ import annotations

from datetime import datetime

from .attestation import AttestationStore
from .envelope import OUT_OF_ENVELOPE, EnvelopeRegister, scope_fault
from .errors import NeuraxisError, UnknownCapabilityError
from .model import (
    AuthorityRequest,
    Capability,
    Decision,
    Obligation,
    Risk,
    Verdict,
    normalise_principal,
    now_utc,
)
from .registry import Registry
from .resolver import BandResolver
from .waiver import WaiverRegister

# Controls whose presence in a band's requirements implies a standing duty on
# every ALLOW issued for that band.
_CONTROL_OBLIGATIONS: dict[str, Obligation] = {
    "GV-03": Obligation.EMIT_EVIDENCE,
    "GV-04": Obligation.INDEPENDENT_VERIFICATION,
    "GV-05": Obligation.TESTED_ROLLBACK,
    "GV-06": Obligation.BOUNDED_SCOPE,
    "GV-07": Obligation.HUMAN_RATIFICATION,
    "GV-09": Obligation.PROVENANCE_BINDING,
}


class GovernanceGate:
    """Blocking authority check for one capability invocation."""

    def __init__(
        self,
        registry: Registry,
        attestations: AttestationStore,
        waivers: WaiverRegister | None = None,
        envelopes: EnvelopeRegister | None = None,
    ) -> None:
        self.registry = registry
        self.attestations = attestations
        self.waivers = waivers if waivers is not None else WaiverRegister.empty(
            registry.waiver_policy
        )
        # An absent register is an empty one, not an absent check: an
        # envelope-bounded capability with no envelope on file is denied, which
        # is the correct reading of "declared in advance".
        self.envelopes = envelopes if envelopes is not None else EnvelopeRegister.empty(
            registry.envelope_policy
        )
        self.resolver = BandResolver(registry, attestations, self.waivers)

    # ---- public API ----------------------------------------------------

    def evaluate(self, request: AuthorityRequest, *, at: datetime | None = None) -> Verdict:
        """Return a verdict. Never raises for request-level problems."""
        at = at or now_utc()
        try:
            return self._evaluate(request, at)
        except UnknownCapabilityError as exc:
            return self._deny(request.capability, None, [str(exc)])
        except NeuraxisError as exc:
            return self._deny(request.capability, None, [f"gate fault, denying: {exc}"])
        except Exception as exc:  # noqa: BLE001 - deliberate catch-all
            # Fail closed on anything unanticipated. An unexpected exception in
            # the gate must not become an implicit allow in the caller.
            return self._deny(request.capability, None, [f"unexpected gate fault, denying: {exc!r}"])

    # ---- evaluation chain ----------------------------------------------

    def _evaluate(self, request: AuthorityRequest, at: datetime) -> Verdict:
        capability = self.registry.capability(request.capability)  # raises if unknown
        band_id = capability.band
        band = self.registry.band(band_id)

        # --- Role: is this role granted the band at all?
        granting_roles = self.registry.roles_granting(band_id)
        if request.role not in granting_roles:
            if granting_roles:
                return Verdict(
                    decision=Decision.DELEGATE,
                    capability=capability.id,
                    band=band_id,
                    reasons=(
                        f"role {request.role!r} is not granted {band_id}",
                        f"delegate to a role holding it: {', '.join(granting_roles)}",
                    ),
                )
            return self._deny(
                capability.id, band_id, [f"no role is granted {band_id}; capability unreachable"]
            )

        # --- Authority: band attainment, reported at the root blocker.
        #
        # Claimed identities are passed down because a waiver never licenses
        # its own issuer or accountable principal. Attainment is therefore a
        # function of who is asking, not of the registry alone.
        claimed = frozenset(request.claimed_identities)
        # One traversal, one instant, one cache: the blocker and the waivers
        # the closure rests on must be the same evaluation, or an ALLOW can be
        # reported as unconditional while resting on a waiver.
        blocker, waivers = self.resolver.authority(band_id, at=at, claimed=claimed)
        if blocker is not None:
            headline = (
                f"{band_id} is not attained"
                if blocker.band == band_id
                else f"{band_id} requires {blocker.band}, which is not attained"
            )
            reasons = [headline, *blocker.reasons]
            return Verdict(
                decision=Decision.DENY,
                capability=capability.id,
                band=band_id,
                reasons=tuple(reasons),
                missing_controls=blocker.missing_controls,
            )

        # `waivers` is carried on every non-DENY verdict so that a conditional
        # authority is recorded as conditional wherever the verdict lands,
        # including in the evidence sink.
        #
        # Obligations are unchanged by a waiver. A waiver says a control cannot
        # currently be proven at programme level; it does not say an individual
        # request need not comply. Reading it the other way would let one
        # signature switch off per-request enforcement, which is the inverse of
        # what an exception path is for.
        obligations = self._obligations(band.requires)

        # --- Scope: an envelope-bounded capability must name a declared bound
        # and stay inside it (ILR-001-DR D-01).
        if capability.envelope_bounded:
            verdict = self._check_envelope(request, capability, band_id, obligations, at)
            if verdict is not None:
                return verdict

        # --- Evidence requirement: obligations the request must already satisfy.
        if Obligation.INDEPENDENT_VERIFICATION in obligations:
            verdict = self._check_verifier_independence(request, capability.id, band_id)
            if verdict is not None:
                return verdict

        if Obligation.TESTED_ROLLBACK in obligations and not request.rollback_tested:
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{band_id} requires GV-05 reversibility; request declares no tested rollback",
                    "NX-INV-3: untested rollback counts as none",
                ],
            )

        # --- Ratification: non-delegable floor and GV-07 bands.
        needs_ratification = (
            capability.id in self.registry.non_delegable
            or Obligation.HUMAN_RATIFICATION in obligations
        )
        # Stripped: a whitespace-only reference is not a reference. The gate
        # cannot yet verify that the reference resolves to a real ratification
        # record — see "known limits" in the README — but it can refuse a blank.
        if needs_ratification and not (request.ratification_ref or "").strip():
            why = (
                f"{capability.id} is on the non-delegable floor"
                if capability.id in self.registry.non_delegable
                else f"{band_id} requires GV-07 human ratification"
            )
            return Verdict(
                decision=Decision.WAIT_FOR_AUTHORITY,
                capability=capability.id,
                band=band_id,
                reasons=(why, "automation may propose; it may not merge"),
                obligations=obligations,
                waivers=waivers,
            )

        # --- Risk: escalate above the configured rank even when attained.
        if request.risk.rank >= self.registry.escalate_at_risk.rank:
            return Verdict(
                decision=Decision.ESCALATE,
                capability=capability.id,
                band=band_id,
                reasons=(
                    f"risk {request.risk.value} at or above escalation threshold "
                    f"{self.registry.escalate_at_risk.value}",
                ),
                obligations=obligations,
                waivers=waivers,
            )

        reasons = [
            f"{band_id} attained; {request.role} granted; "
            f"{len(band.requires)} controls current"
        ]
        if waivers:
            # Overwrite rather than append: "controls current" is false when a
            # control is waived, and a true clause beside a false one still
            # reads as a clean attainment to anyone skimming the first line.
            reasons = [
                f"{band_id} attained conditionally; {request.role} granted; "
                f"authority rests on waiver(s) {', '.join(waivers)}",
                "conditional authority: at least one control is unproven and lapses "
                "with the waiver",
            ]
        if capability.envelope_bounded and request.envelope_ref:
            reasons.append(
                f"bounded by envelope {request.envelope_ref} "
                f"(scope {request.scope}; "
                f"{len(request.adjustments)} adjustment(s) inside the declared limits)"
            )
        return Verdict(
            decision=Decision.ALLOW,
            capability=capability.id,
            band=band_id,
            reasons=tuple(reasons),
            obligations=obligations,
            waivers=waivers,
        )

    # ---- helpers -------------------------------------------------------

    def _check_envelope(
        self,
        request: AuthorityRequest,
        capability: Capability,
        band_id: str,
        obligations: tuple[Obligation, ...],
        at: datetime,
    ) -> Verdict | None:
        """ILR-001-DR D-01. Returns a DENY verdict, or None if the bound holds.

        Every denial here is fail-closed and specific. The specificity is the
        point: "your envelope expired" and "this parameter is not one your
        envelope declares" are different problems, and a denial that cannot
        tell them apart gets resolved by declaring a wider envelope.
        """
        ref = (request.envelope_ref or "").strip()
        if not ref:
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{capability.id} is envelope-bounded and the request names no envelope",
                    "D-01: an adjustment with no bound declared in advance is IL-13b, "
                    "which belongs to BAND-G",
                ],
            )

        # Every denial below opens with OUT_OF_ENVELOPE, including the ones that
        # are not strictly a boundary breach. An expired envelope being hammered
        # is the split being leaned on just as much as an out-of-range value is,
        # and the D-01 trigger counts what it can see.
        envelope = self.envelopes.get(ref)
        if envelope is None:
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: envelope {ref!r} is not on file; an undeclared "
                    "bound is not a bound"
                ],
            )
        if not envelope.is_active(at):
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: envelope {envelope.id} is not active at "
                    f"{at.isoformat()} (declared {envelope.issued_at.isoformat()}, "
                    f"expires {envelope.expires_at.isoformat()})",
                ],
            )
        # Re-checked at use, not only at load. A register built with the default
        # policy and handed to a gate whose registry tightened the ceiling or
        # named its signers would otherwise carry envelopes that registry would
        # have refused -- one wrong constructor call, silently, forever.
        fault = self.envelopes.policy_fault(envelope)
        if fault is not None or not self.registry.envelope_policy.signer_permitted(
            envelope.signed_by
        ):
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: envelope {envelope.id} breaches this registry's "
                    f"envelope policy: {fault or 'signer not on the declared allowlist'}"
                ],
            )
        if envelope.capability != capability.id:
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: envelope {envelope.id} bounds "
                    f"{envelope.capability}, not {capability.id}; an envelope is not "
                    "transferable between capabilities"
                ],
            )
        if not all(envelope.bounds(i) for i in request.claimed_identities):
            # EVERY claimed identity, not any. `performer` is requester-supplied,
            # so `any` would let a caller unlock someone else's envelope by
            # naming them as performer -- and an adjustment made on another
            # principal's behalf is not self-tuning, which is the only thing
            # D-01 admits from Band C.
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: envelope {envelope.id} bounds "
                    f"{envelope.principal!r}, and this request claims "
                    f"{', '.join(sorted(request.claimed_identities))}",
                    "an envelope constrains one principal: tuning on another's behalf, "
                    "or under a bound written for someone else, is not self-tuning",
                ],
            )
        if not request.adjustments:
            # An adjustment that declares no parameter is not an adjustment, and
            # an ALLOW for one would record "0 adjustments inside the declared
            # limits" -- a sentence an auditor reads as a check having passed.
            return self._deny(
                capability.id,
                band_id,
                [
                    f"{OUT_OF_ENVELOPE}: the request declares no adjustment, so there "
                    f"is nothing for {envelope.id} to bound",
                    "D-01: what is not declared cannot be checked, and an undeclared "
                    "change is IL-13b",
                ],
            )

        reasons: list[str] = []
        bad_scope = scope_fault(request.scope)
        if bad_scope is not None:
            reasons.append(bad_scope)
        elif not envelope.covers_target(request.scope):
            reasons.append(
                f"{OUT_OF_ENVELOPE}: scope {request.scope!r} is outside the targets "
                f"{envelope.id} declares ({', '.join(envelope.targets)})"
            )
        reasons.extend(envelope.violations(request.adjustments))
        if reasons:
            return Verdict(
                decision=Decision.DENY,
                capability=capability.id,
                band=band_id,
                reasons=tuple(
                    reasons
                    + [
                        f"D-01: {envelope.id} was signed by {envelope.signed_by}, who is "
                        "not the principal it bounds. Widening it is their decision, "
                        "not this caller's"
                    ]
                ),
                obligations=obligations,
            )
        return None

    def _check_verifier_independence(
        self, request: AuthorityRequest, capability_id: str, band_id: str
    ) -> Verdict | None:
        """NX-INV-2. Returns a DENY verdict, or None if independence holds.

        Compared against every identity the request claims, not just
        `performer`: `performer` is requester-supplied, so naming a fictitious
        performer would otherwise let a caller verify its own work under its
        real identity. Comparison is case-folded and stripped, because
        `"agent-x "` and `"Agent-X"` are the same principal to everyone except
        a raw `==`.
        """
        verifier = (request.verifier or "").strip()
        if not verifier:
            return self._deny(
                capability_id,
                band_id,
                [
                    f"{band_id} requires GV-04 independent verification; no verifier named",
                    "NX-INV-2: verification reliability is zero when unspecified",
                ],
            )
        # Normalised, not merely case-folded: `"agent-x​"` renders
        # identically to `"agent-x"` and would otherwise pass this check with
        # one invisible codepoint, which defeats NX-INV-2 outright.
        claimed = {normalise_principal(i) for i in request.claimed_identities}
        if normalise_principal(verifier) in claimed:
            return self._deny(
                capability_id,
                band_id,
                [
                    f"verifier {verifier!r} is one of the identities this request claims "
                    f"({', '.join(sorted(request.claimed_identities))})",
                    "NX-INV-2: V = 0 when performer and verifier are the same identity",
                ],
            )
        return None

    def _obligations(self, required_controls: tuple[str, ...]) -> tuple[Obligation, ...]:
        found = {_CONTROL_OBLIGATIONS[c] for c in required_controls if c in _CONTROL_OBLIGATIONS}
        return tuple(sorted(found, key=lambda o: o.value))

    @staticmethod
    def _deny(capability: str, band: str | None, reasons: list[str]) -> Verdict:
        return Verdict(
            decision=Decision.DENY,
            capability=capability,
            band=band,
            reasons=tuple(reasons),
        )
