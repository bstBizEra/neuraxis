"""Effective intelligence scorecard.

    I_effective = C x R x L x A x V x G

Its value is the veto, not the number. Because the terms multiply, any term at
zero zeroes the product — the arithmetic statement of "more intelligence is not
more freedom".

Deliberate limitation: multiplying ordinal scores is not statistically
meaningful, and `effective` must not be reported as a headline figure. The only
supported use is `gate_band()`, which blocks a band when any term falls below
its threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .registry import Registry

_TERMS = ("C", "R", "L", "A", "V", "G")
_TERM_NAMES = {
    "C": "cognitive capability (bands attained)",
    "R": "reasoning quality (sealed-exam first-pass rate)",
    "L": "learning capability (lesson yield x retrieval precision)",
    "A": "action capability (completed without escalation)",
    "V": "verification reliability (independence of the judge)",
    "G": "governance integrity (passing attestations / required)",
}


@dataclass(frozen=True)
class Scorecard:
    """Six terms on [0, 1]. Construct via `measure` rather than by hand."""

    C: float
    R: float
    L: float
    A: float
    V: float
    G: float

    def __post_init__(self) -> None:
        for term in _TERMS:
            value = getattr(self, term)
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"scorecard term {term} must be within [0, 1], got {value}")

    @property
    def effective(self) -> float:
        """The product. Diagnostic only — never a reported KPI."""
        result = 1.0
        for term in _TERMS:
            result *= float(getattr(self, term))
        return result

    @property
    def zeroed_terms(self) -> tuple[str, ...]:
        """Terms at exactly zero — each one vetoes everything downstream."""
        return tuple(t for t in _TERMS if float(getattr(self, t)) == 0.0)

    def gate_band(self, registry: Registry, band_id: str) -> tuple[bool, tuple[str, ...]]:
        """Does this scorecard permit operating at `band_id`?

        Returns (permitted, reasons). Thresholds come from the registry, so
        raising the bar is a kernel change rather than a code change.
        """
        thresholds = registry.threshold(band_id)
        failures: list[str] = []
        for term in self.zeroed_terms:
            failures.append(f"{term} = 0 ({_TERM_NAMES[term]}) vetoes all operation")
        for term, minimum in thresholds.items():
            value = float(getattr(self, term))
            if value < float(minimum):
                failures.append(
                    f"{term} = {value:.2f} below {band_id} threshold {float(minimum):.2f} "
                    f"({_TERM_NAMES[term]})"
                )
        deduped = tuple(dict.fromkeys(failures))
        if deduped:
            return False, deduped
        return True, (f"{band_id}: all scorecard thresholds met",)

    def to_dict(self) -> dict[str, Any]:
        return {
            **{term: round(float(getattr(self, term)), 4) for term in _TERMS},
            "effective": round(self.effective, 6),
            "zeroed_terms": list(self.zeroed_terms),
        }


def measure(
    *,
    bands_attained: int,
    bands_total: int,
    exam_first_pass_rate: float,
    lesson_yield: float,
    retrieval_precision: float,
    tasks_completed: int,
    tasks_attempted: int,
    independent_verification_coverage: float,
    performer_is_verifier: bool,
    controls_passing: int,
    controls_required: int,
) -> Scorecard:
    """Build a scorecard from raw measurements.

    `performer_is_verifier` forces V to exactly zero. This is the single most
    consequential rule in the model: a system that judges its own work has no
    verification, whatever its coverage statistics say.
    """
    if bands_total <= 0:
        raise ValueError("bands_total must be positive")
    if tasks_attempted < 0 or tasks_completed < 0:
        raise ValueError("task counts must be non-negative")
    if tasks_completed > tasks_attempted:
        raise ValueError("tasks_completed cannot exceed tasks_attempted")
    if controls_required < 0 or controls_passing < 0:
        raise ValueError("control counts must be non-negative")
    if controls_passing > controls_required:
        raise ValueError("controls_passing cannot exceed controls_required")

    return Scorecard(
        C=_clamp(bands_attained / bands_total),
        R=_clamp(exam_first_pass_rate),
        L=_clamp(lesson_yield) * _clamp(retrieval_precision),
        A=_clamp(tasks_completed / tasks_attempted) if tasks_attempted else 0.0,
        V=0.0 if performer_is_verifier else _clamp(independent_verification_coverage),
        G=_clamp(controls_passing / controls_required) if controls_required else 1.0,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
