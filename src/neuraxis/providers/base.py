"""Provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProviderOutcome(str, Enum):
    """A provider says PASS, FAIL, or that it is not wired to a real source.

    UNWIRED is distinct from FAIL on purpose. Both deny the control — nothing
    is attested either way — but they mean different things to an operator:
    FAIL is "the check ran and the control does not hold", UNWIRED is "this
    check has no source yet". Collapsing them would hide the roadmap inside a
    wall of red.
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNWIRED = "UNWIRED"

    @property
    def attests(self) -> bool:
        return self is ProviderOutcome.PASS


@dataclass(frozen=True)
class ProviderResult:
    """What a provider returns. `evidence_ref` is mandatory for a PASS."""

    outcome: ProviderOutcome
    evidence_ref: str
    detail: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def passed(cls, evidence_ref: str, detail: str, **facts: Any) -> "ProviderResult":
        return cls(ProviderOutcome.PASS, evidence_ref, detail, facts)

    @classmethod
    def failed(cls, detail: str, evidence_ref: str = "", **facts: Any) -> "ProviderResult":
        return cls(ProviderOutcome.FAIL, evidence_ref, detail, facts)

    @classmethod
    def unwired(cls, detail: str, **facts: Any) -> "ProviderResult":
        return cls(ProviderOutcome.UNWIRED, "", detail, facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "evidence_ref": self.evidence_ref,
            "detail": self.detail,
            "facts": dict(self.facts),
        }


class Provider(ABC):
    """Base class for attestation providers.

    Subclasses implement three methods, and the harness refuses to honour a
    PASS unless all three behave. `positive_control` and `vacuity_probe` are
    not optional extras — they are what distinguishes a check from a constant.
    """

    control: str = ""
    name: str = ""

    def __init__(self, **config: Any) -> None:
        self.config = config
        if not self.control or not self.name:
            raise ValueError(f"{type(self).__name__} must declare `control` and `name`")

    @abstractmethod
    def positive_control(self) -> bool:
        """Prove the check is live.

        Returns True when the provider can reach its source and would be able
        to observe a passing condition. A denial from a dead check proves
        nothing, so a False here makes the whole run FAIL.
        """

    @abstractmethod
    def vacuity_probe(self) -> ProviderResult:
        """Run the check against a condition that MUST fail.

        If this returns PASS, the check cannot discriminate and is therefore
        not a check. This is the direct answer to the KBS-001 finding that a
        probe returning the same result for a powerful and a powerless identity
        is not a test.
        """

    @abstractmethod
    def check(self) -> ProviderResult:
        """The actual assertion about the control."""

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<{type(self).__name__} {self.control} {self.name}>"


class UnwiredProvider(Provider):
    """A provider whose real source does not exist yet.

    Declared rather than omitted, so `neuraxis providers` shows the true
    coverage of the control set and `assure` refuses to attest the control
    instead of silently skipping it. The blocker is named so the output doubles
    as a live view of the roadmap.
    """

    def __init__(self, control: str, name: str, blocked_on: str, **config: Any) -> None:
        self.control = control
        self.name = name
        self.blocked_on = blocked_on
        super().__init__(**config)

    def positive_control(self) -> bool:
        return False

    def vacuity_probe(self) -> ProviderResult:
        return ProviderResult.failed("unwired providers cannot pass anything")

    def check(self) -> ProviderResult:
        return ProviderResult.unwired(
            f"{self.name} has no source yet; blocked on {self.blocked_on}",
            blocked_on=self.blocked_on,
        )
