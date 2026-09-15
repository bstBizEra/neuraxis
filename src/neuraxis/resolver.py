"""Band attainment resolution.

A band is attained when, and only when:

  1. every band it depends on is attained (transitively), and
  2. every governance control it requires holds a current passing attestation.

This is the Capability-Authority Gate matrix (ILR-001 section 5.3) evaluated
against live attestations rather than read from a table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from .attestation import AttestationStore
from .model import BandStatus
from .registry import Registry


class BandResolver:
    """Computes band attainment. Stateless between calls; cheap to construct."""

    def __init__(self, registry: Registry, attestations: AttestationStore) -> None:
        self.registry = registry
        self.attestations = attestations

    def status(self, band_id: str, *, at: datetime | None = None) -> BandStatus:
        """Attainment of a single band, with the reasons it is or is not."""
        band = self.registry.band(band_id)
        missing = self.attestations.missing(band.requires, self.registry.max_age_for, at=at)

        blocked_by: list[str] = []
        for dep in band.depends_on:
            if not self.status(dep, at=at).attained:
                blocked_by.append(dep)

        reasons: list[str] = []
        for control in missing:
            reasons.append(
                self.attestations.explain(control, self.registry.max_age_for(control), at=at)
            )
        for dep in blocked_by:
            reasons.append(f"{dep}: prerequisite band not attained")

        attained = not missing and not blocked_by
        if attained:
            reasons.append(
                f"{band_id}: attained ({len(band.requires)} controls current, "
                f"{len(band.depends_on)} prerequisites met)"
            )

        return BandStatus(
            band=band_id,
            attained=attained,
            missing_controls=missing,
            blocked_by=tuple(blocked_by),
            reasons=tuple(reasons),
        )

    def all_statuses(self, *, at: datetime | None = None) -> Mapping[str, BandStatus]:
        """Attainment of every band, in registry order."""
        return {bid: self.status(bid, at=at) for bid in self.registry.bands}

    def attained_bands(self, *, at: datetime | None = None) -> tuple[str, ...]:
        return tuple(bid for bid, st in self.all_statuses(at=at).items() if st.attained)

    def first_blocker(self, band_id: str, *, at: datetime | None = None) -> BandStatus | None:
        """The earliest unattained band in `band_id`'s dependency closure.

        Reporting the root blocker rather than the requested band is what makes
        the CLI output actionable: BAND-G is never the real problem.
        """
        for candidate in self.registry.band_closure(band_id):
            status = self.status(candidate, at=at)
            if not status.attained:
                return status
        return None
