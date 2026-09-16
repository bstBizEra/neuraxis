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
from .errors import NeuraxisError, UnknownCapabilityError
from .model import AuthorityRequest, Decision, Obligation, Risk, Verdict, now_utc
from .registry import Registry
from .resolver import BandResolver

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

    def __init__(self, registry: Registry, attestations: AttestationStore) -> None:
        self.registry = registry
        self.attestations = attestations
        self.resolver = BandResolver(registry, attestations)

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
        blocker = self.resolver.first_blocker(band_id, at=at)
        if blocker is not None:
            reasons = [f"{band_id} requires {blocker.band}, which is not attained", *blocker.reasons]
            return Verdict(
                decision=Decision.DENY,
                capability=capability.id,
                band=band_id,
                reasons=tuple(reasons),
                missing_controls=blocker.missing_controls,
            )

        obligations = self._obligations(band.requires)

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
            )

        return Verdict(
            decision=Decision.ALLOW,
            capability=capability.id,
            band=band_id,
            reasons=(
                f"{band_id} attained; {request.role} granted; "
                f"{len(band.requires)} controls current",
            ),
            obligations=obligations,
        )

    # ---- helpers -------------------------------------------------------

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
        claimed = {i.casefold() for i in request.claimed_identities}
        if verifier.casefold() in claimed:
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
