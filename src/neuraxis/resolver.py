"""Band attainment resolution.

A band is attained when, and only when:

  1. every band it depends on is attained (transitively), and
  2. every governance control it requires either holds a current passing
     attestation, or is covered by an active waiver that may license this
     caller (ILR-001-DR D-05).

This is the Capability-Authority Gate matrix (ILR-001 section 5.3) evaluated
against live attestations rather than read from a table.

Attainment under waiver is still attainment -- that is what an exception path
means -- but it is never reported as though the control held. `BandStatus`
carries the waived controls and the waiver ids separately, and every caller
that prints or records a status is expected to say so, because a band shown as
plainly attained while a control is unproven is the stale-state surface this
project exists to avoid building.

One evaluation, one instant. `at` is resolved once at the entry point and
threaded down, and every band is computed at most once per call. Both matter
for the same reason: the gate is synchronous and blocking (D-03), so an
evaluation that re-expands the dependency graph -- or that asks the clock
again halfway through and gets a different answer -- is a latency problem
and a consistency problem at the point where a caller is waiting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from .attestation import AttestationStore
from .model import BandStatus, now_utc
from .registry import Registry
from .waiver import WaiverRegister


class BandResolver:
    """Computes band attainment. Stateless between calls; cheap to construct."""

    def __init__(
        self,
        registry: Registry,
        attestations: AttestationStore,
        waivers: WaiverRegister | None = None,
    ) -> None:
        self.registry = registry
        self.attestations = attestations
        self.waivers = waivers if waivers is not None else WaiverRegister.empty(
            registry.waiver_policy
        )

    # ---- public API ----------------------------------------------------

    def status(
        self,
        band_id: str,
        *,
        at: datetime | None = None,
        claimed: Iterable[str] = (),
    ) -> BandStatus:
        """Attainment of a single band, with the reasons it is or is not.

        `claimed` is every identity the caller acts as. A waiver never licenses
        its own issuer or the principal accountable for it, so the answer is
        caller-dependent by design. An empty `claimed` is reporting mode: it
        shows what the waiver set licenses for someone, which is the right
        answer for `status` and the wrong one for the gate. The gate always
        passes the request's claimed identities.
        """
        at = at or now_utc()
        return self._status(band_id, at, frozenset(claimed), {})

    def all_statuses(
        self, *, at: datetime | None = None, claimed: Iterable[str] = ()
    ) -> Mapping[str, BandStatus]:
        """Attainment of every band, in registry order."""
        at = at or now_utc()
        cache: dict[str, BandStatus] = {}
        key = frozenset(claimed)
        return {bid: self._status(bid, at, key, cache) for bid in self.registry.bands}

    def attained_bands(
        self, *, at: datetime | None = None, claimed: Iterable[str] = ()
    ) -> tuple[str, ...]:
        return tuple(
            bid for bid, st in self.all_statuses(at=at, claimed=claimed).items() if st.attained
        )

    def first_blocker(
        self, band_id: str, *, at: datetime | None = None, claimed: Iterable[str] = ()
    ) -> BandStatus | None:
        """The earliest unattained band in `band_id`'s dependency closure."""
        return self.authority(band_id, at=at, claimed=claimed)[0]

    def waivers_in_closure(
        self, band_id: str, *, at: datetime | None = None, claimed: Iterable[str] = ()
    ) -> tuple[str, ...]:
        """Ids of every waiver this band's attainment rests on, transitively."""
        return self.authority(band_id, at=at, claimed=claimed)[1]

    def authority(
        self, band_id: str, *, at: datetime | None = None, claimed: Iterable[str] = ()
    ) -> tuple[BandStatus | None, tuple[str, ...]]:
        """The root blocker (or None) and every waiver the closure rests on.

        Both in one traversal, at one instant, from one cache. Computing them
        separately is how a band comes back attained from the first call and
        waiver-free from the second: the answers disagree, and the verdict
        then reports an unconditional ALLOW resting on a waiver.
        """
        at = at or now_utc()
        key = frozenset(claimed)
        cache: dict[str, BandStatus] = {}
        blocker: BandStatus | None = None
        waiver_ids: list[str] = []
        for candidate in self.registry.band_closure(band_id):
            status = self._status(candidate, at, key, cache)
            if not status.attained and blocker is None:
                blocker = status
            for wid in status.waiver_ids:
                if wid not in waiver_ids:
                    waiver_ids.append(wid)
        if blocker is not None:
            # A blocked closure grants nothing, so it rests on no waiver.
            return blocker, ()
        return None, tuple(waiver_ids)

    # ---- internals -----------------------------------------------------

    def _status(
        self,
        band_id: str,
        at: datetime,
        claimed: frozenset[str],
        cache: dict[str, BandStatus],
    ) -> BandStatus:
        cached = cache.get(band_id)
        if cached is not None:
            return cached

        band = self.registry.band(band_id)
        unmet = self.attestations.missing(band.requires, self.registry.max_age_for, at=at)
        void = self.waivers.void_reason(at)

        reasons: list[str] = []
        missing: list[str] = []
        waived: list[str] = []
        waiver_ids: list[str] = []

        for control in unmet:
            waiver = self.waivers.covering(control, band_id, at=at, claimed=claimed)
            if waiver is not None:
                waived.append(control)
                if waiver.id not in waiver_ids:
                    waiver_ids.append(waiver.id)
                reasons.append(
                    f"{control}: not attested, waived by {waiver.id} until "
                    f"{waiver.expires_at.isoformat()} "
                    f"(accountable: {waiver.accountable}; "
                    f"compensating: {waiver.compensating_control})"
                )
                continue
            missing.append(control)
            reasons.append(
                self.attestations.explain(control, self.registry.max_age_for(control), at=at)
            )
            withheld = self.waivers.excluded(control, band_id, at=at, claimed=claimed)
            if withheld is not None:
                reasons.append(
                    f"{control}: waiver {withheld.id} covers this band but cannot license "
                    f"its own issuer or accountable principal "
                    f"({withheld.issued_by}, {withheld.accountable})"
                )
            elif void is not None:
                reasons.append(f"{control}: {void}")

        blocked_by: list[str] = []
        for dep in band.depends_on:
            dep_status = self._status(dep, at, claimed, cache)
            if not dep_status.attained:
                blocked_by.append(dep)
                reasons.append(f"{dep}: prerequisite band not attained")
            elif dep_status.waived_controls:
                reasons.append(
                    f"{dep}: prerequisite attained under waiver "
                    f"({', '.join(dep_status.waived_controls)} unproven)"
                )

        attained = not missing and not blocked_by
        if attained:
            if waived:
                reasons.append(
                    f"{band_id}: attained conditionally -- "
                    f"{len(band.requires) - len(waived)} of {len(band.requires)} controls "
                    f"current, {len(waived)} waived ({', '.join(waived)})"
                )
            else:
                reasons.append(
                    f"{band_id}: attained ({len(band.requires)} controls current, "
                    f"{len(band.depends_on)} prerequisites met)"
                )

        status = BandStatus(
            band=band_id,
            attained=attained,
            missing_controls=tuple(missing),
            blocked_by=tuple(blocked_by),
            reasons=tuple(reasons),
            waived_controls=tuple(waived),
            waiver_ids=tuple(waiver_ids),
        )
        cache[band_id] = status
        return status
