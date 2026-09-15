"""Provider harness — where the four conformance rules are enforced.

The harness is the reason a provider cannot lie by accident. A provider author
who forgets to handle an error, or writes a check that always passes, produces
a FAIL here rather than a green attestation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..errors import NeuraxisError
from ..model import Attestation, now_utc
from .base import Provider, ProviderOutcome, ProviderResult


class ConformanceError(NeuraxisError):
    """A provider violated a conformance rule. Always results in FAIL."""


@dataclass(frozen=True)
class ProviderRun:
    """The outcome of running one provider through the harness."""

    control: str
    provider: str
    result: ProviderResult
    conformance: tuple[str, ...]
    ran_at: datetime

    @property
    def attests(self) -> bool:
        return self.result.outcome.attests

    def to_attestation(self, *, at: datetime | None = None) -> Attestation:
        """Convert to a recordable attestation.

        UNWIRED and FAIL both record `result=False`: nothing is attested. The
        distinction is preserved in `evidence_ref` so an operator reading the
        log can tell a failing control from an unbuilt one.
        """
        outcome = self.result.outcome
        return Attestation(
            control=self.control,
            result=outcome.attests,
            issued_at=at or self.ran_at,
            issuer=self.provider,
            evidence_ref=self.result.evidence_ref or f"{outcome.value.lower()}:{self.provider}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "control": self.control,
            "provider": self.provider,
            "attests": self.attests,
            "conformance": list(self.conformance),
            "ran_at": self.ran_at.isoformat(),
            **self.result.to_dict(),
        }


def run_provider(provider: Provider, *, at: datetime | None = None) -> ProviderRun:
    """Run a provider under the four conformance rules.

    Never raises. Every failure path — including a provider that throws —
    becomes a FAIL, because a harness that propagates an exception hands the
    caller an ambiguous result, and ambiguity is how vacuous checks survive.
    """
    ran_at = at or now_utc()
    violations: list[str] = []

    def fail(detail: str, **facts: Any) -> ProviderRun:
        return ProviderRun(
            control=provider.control,
            provider=provider.name,
            result=ProviderResult.failed(detail, **facts),
            conformance=tuple(violations),
            ran_at=ran_at,
        )

    # Rule 1 (fail closed) wraps rules 2-4: any exception below lands here.
    try:
        # Rule 2 — positive control. An UNWIRED provider is expected to fail
        # this, and reports as UNWIRED rather than as a conformance violation.
        try:
            live = bool(provider.positive_control())
        except Exception as exc:  # noqa: BLE001
            violations.append("positive-control-raised")
            return fail(f"positive control raised: {exc!r}")

        if not live:
            probe = provider.check()
            if probe.outcome is ProviderOutcome.UNWIRED:
                return ProviderRun(
                    control=provider.control,
                    provider=provider.name,
                    result=probe,
                    conformance=("unwired",),
                    ran_at=ran_at,
                )
            violations.append("positive-control-failed")
            return fail(
                "positive control did not pass; the check is not live, so any "
                "result it returns is meaningless"
            )

        # Rule 3 — vacuity probe. A check that cannot fail is not a check.
        try:
            vacuity = provider.vacuity_probe()
        except Exception as exc:  # noqa: BLE001
            violations.append("vacuity-probe-raised")
            return fail(f"vacuity probe raised: {exc!r}")

        if vacuity.outcome is ProviderOutcome.PASS:
            violations.append("vacuous")
            return fail(
                "vacuity probe PASSED — the check returns the same result for a "
                "condition that must fail, so it discriminates nothing"
            )

        # The check itself.
        try:
            result = provider.check()
        except Exception as exc:  # noqa: BLE001
            violations.append("check-raised")
            return fail(f"check raised: {exc!r}")

        if not isinstance(result, ProviderResult):
            violations.append("bad-return-type")
            return fail(f"check returned {type(result).__name__}, expected ProviderResult")

        # Rule 4 — evidence. A PASS without a reference is an assertion.
        if result.outcome is ProviderOutcome.PASS and not result.evidence_ref.strip():
            violations.append("no-evidence")
            return fail("PASS carried no evidence reference; an unreferenced pass is an assertion")

        return ProviderRun(
            control=provider.control,
            provider=provider.name,
            result=result,
            conformance=tuple(violations),
            ran_at=ran_at,
        )

    except Exception as exc:  # noqa: BLE001 - deliberate catch-all
        violations.append("harness-fault")
        return fail(f"unexpected harness fault, failing closed: {exc!r}")
