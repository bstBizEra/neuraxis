"""Core value types for BST Neuraxis.

All types are frozen: a verdict, once produced, must not be mutated by anything
downstream.

**Nothing in this package writes a verdict to the evidence sink.** That edge
does not exist yet, which is why the obligations attached to an ALLOW are
advisory rather than enforced — no later provider cycle can observe that the
ALLOW was issued, so none can detect that its obligations went undischarged.
See "known limits" in the README.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

UTC = timezone.utc

#: Fields a non-Python caller may send. Exposed through `neuraxis contract`
#: so clients assert against it instead of hard-coding their own copy.
REQUEST_REQUIRED_FIELDS = ("intent", "identity", "role", "capability", "scope")
REQUEST_OPTIONAL_FIELDS = (
    "risk", "performer", "verifier", "rollback_tested", "ratification_ref",
)
REQUEST_FIELDS = REQUEST_REQUIRED_FIELDS + REQUEST_OPTIONAL_FIELDS


def now_utc() -> datetime:
    """Single clock source, so tests can reason about freshness deterministically."""
    return datetime.now(UTC)


class Decision(str, Enum):
    """Governance gate verdicts (ILR-001 section 6.4)."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    DELEGATE = "DELEGATE"
    ESCALATE = "ESCALATE"
    WAIT_FOR_AUTHORITY = "WAIT_FOR_AUTHORITY"

    @property
    def permits_action(self) -> bool:
        """Only ALLOW permits the caller to act. Everything else blocks."""
        return self is Decision.ALLOW


class Risk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[self.value]


class Obligation(str, Enum):
    """Duties attached to an ALLOW.

    Three are checked at the gate: INDEPENDENT_VERIFICATION, TESTED_ROLLBACK
    and HUMAN_RATIFICATION. The rest — EMIT_EVIDENCE, BOUNDED_SCOPE,
    PROVENANCE_BINDING — are **labels, not controls**: they name a duty the
    caller owes, and nothing in this package verifies it was discharged,
    because no verdict is ever written back for a later cycle to audit.

    Stated plainly here because the gap is the kind a reader assumes away.
    """

    EMIT_EVIDENCE = "emit-evidence-record"
    INDEPENDENT_VERIFICATION = "independent-verification"
    TESTED_ROLLBACK = "tested-rollback"
    BOUNDED_SCOPE = "bounded-scope"
    PROVENANCE_BINDING = "provenance-binding"
    HUMAN_RATIFICATION = "human-ratification"


@dataclass(frozen=True)
class Capability:
    """One IL-nn entry."""

    id: str
    name: str
    band: str
    question: str


@dataclass(frozen=True)
class GVControl:
    """One GV-nn governance control.

    `max_age` is the control's own attestation window. Windows differ by cost:
    a kernel-boundary probe is cheap and proves little if it is a week old; a
    rollback drill is disruptive, and demanding daily proof of it guarantees it
    gets stubbed — which is the vacuous-check failure in a different costume.
    """

    id: str
    name: str
    attestation: str
    max_age: timedelta


_INVISIBLE = frozenset({"Cf", "Cc", "Cs", "Co", "Cn"})


def has_invisible(text: str) -> bool:
    """True if `text` contains a format, control or unassigned codepoint.

    U+200B, U+FEFF and U+00AD are invisible to a reviewer, survive `strip()`,
    and make two principal names that render identically compare unequal.
    A principal name containing one is rejected rather than folded, because a
    name nobody can see is not a name anybody can be held to.
    """
    return any(unicodedata.category(ch) in _INVISIBLE for ch in text)


def normalise_principal(text: str) -> str:
    """Fold a principal name to a comparison key.

    Deliberately aggressive: NFKC, then invisible codepoints dropped, then
    case-folded, then combining marks stripped. Every step can only make two
    distinct strings collide, never separate two that matched -- and in both
    places this key is used (verifier independence, and the self-waiver ban)
    a collision produces a denial. Over-folding therefore fails closed, while
    under-folding is the U+200B bypass that lets a principal verify or license
    itself with one invisible character.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) not in _INVISIBLE)
    folded = unicodedata.normalize("NFD", folded.casefold())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    return folded.strip()


@dataclass(frozen=True)
class Band:
    """A band of capabilities plus the controls that license them."""

    id: str
    capabilities: tuple[str, ...]
    requires: tuple[str, ...]
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class Attestation:
    """Evidence that a governance control currently holds.

    `result` False is recorded, not discarded: a failing attestation is the
    signal that a band must close, and silently dropping it would let a band
    stay open on a stale pass.

    `provenance` distinguishes a result a provider established from one a human
    asserted. Without it the two are indistinguishable on disk, and a typed
    assertion satisfies a control that has a real check — which is the whole
    mechanism defeated by a shell loop.
    """

    control: str
    result: bool
    issued_at: datetime
    issuer: str
    evidence_ref: str
    provenance: str = "manual"

    def __post_init__(self) -> None:
        if self.issued_at.tzinfo is None:
            raise ValueError(f"attestation {self.control}: issued_at must be tz-aware")
        if self.provenance not in ("provider", "manual"):
            raise ValueError(
                f"attestation {self.control}: provenance must be 'provider' or 'manual'"
            )

    def is_current(self, max_age: timedelta, *, at: datetime | None = None) -> bool:
        """Current means: passing, not expired, and not future-dated.

        Future-dating is rejected rather than tolerated. A clock that can be
        pushed forward is a way to keep a dead attestation alive indefinitely.
        """
        at = at or now_utc()
        if not self.result:
            return False
        age = at - self.issued_at
        if age < timedelta(0):
            return False
        return age <= max_age


@dataclass(frozen=True)
class AuthorityRequest:
    """The input to the governance gate (ILR-001 section 6.4).

    Field order mirrors the spec's chain: intent, identity, role, authority,
    scope, risk, evidence requirement.
    """

    intent: str
    identity: str
    role: str
    capability: str
    scope: str
    risk: Risk = Risk.LOW
    performer: str | None = None
    verifier: str | None = None
    rollback_tested: bool = False
    ratification_ref: str | None = None
    requested_at: datetime = field(default_factory=now_utc)

    def __post_init__(self) -> None:
        for name in REQUEST_REQUIRED_FIELDS:
            if not str(getattr(self, name)).strip():
                raise ValueError(f"AuthorityRequest.{name} must be non-empty")

    @property
    def effective_performer(self) -> str:
        return (self.performer or self.identity).strip()

    @property
    def claimed_identities(self) -> tuple[str, ...]:
        """Every principal this request claims to act as.

        Verifier independence is checked against all of them. Comparing only
        against `performer` lets a requester name a fictitious performer and
        verify its own work under its real identity.
        """
        return tuple(
            {self.identity.strip(), self.effective_performer} - {""}
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorityRequest":
        """Parse the JSON contract used by non-Python callers (maw-js agents)."""
        known = set(REQUEST_FIELDS)
        unknown = set(data) - known - {"requested_at"}
        if unknown:
            raise ValueError(f"unknown request fields: {sorted(unknown)}")
        payload = {k: data[k] for k in known if k in data}
        if "risk" in payload:
            payload["risk"] = Risk(str(payload["risk"]).upper())
        if "rollback_tested" in payload:
            # Strict. `"false"` is a non-empty string and therefore truthy, so
            # a JSON caller could satisfy NX-INV-3 by spelling the word.
            value = payload["rollback_tested"]
            if not isinstance(value, bool):
                raise ValueError(
                    f"rollback_tested must be a JSON boolean, got {type(value).__name__} "
                    f"({value!r}); a truthy string is not a tested rollback"
                )
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Verdict:
    """The gate's answer. Immutable, serialisable, and an evidence record."""

    decision: Decision
    capability: str
    band: str | None
    reasons: tuple[str, ...]
    obligations: tuple[Obligation, ...] = ()
    missing_controls: tuple[str, ...] = ()
    evaluated_at: datetime = field(default_factory=now_utc)
    # Waivers this verdict rests on, transitively through the band closure.
    # A non-empty tuple means the authority granted is conditional: one or
    # more controls are unproven and licensed only until the waiver expires.
    waivers: tuple[str, ...] = ()

    @property
    def permits_action(self) -> bool:
        return self.decision.permits_action

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        data["obligations"] = [o.value for o in self.obligations]
        data["reasons"] = list(self.reasons)
        data["missing_controls"] = list(self.missing_controls)
        data["evaluated_at"] = self.evaluated_at.isoformat()
        data["waivers"] = list(self.waivers)
        return data

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass(frozen=True)
class BandStatus:
    """Why a band is or is not attained. Reasons are always populated."""

    band: str
    attained: bool
    missing_controls: tuple[str, ...]
    blocked_by: tuple[str, ...]
    reasons: tuple[str, ...]
    waived_controls: tuple[str, ...] = ()
    # Ids of the waivers this band's own attainment consumed. Carried rather
    # than re-derived: asking the register a second time can return a
    # different answer (a lapse, or the active cap tripping between calls),
    # and the disagreement would silently drop the waiver from the record.
    waiver_ids: tuple[str, ...] = ()

    @property
    def conditional(self) -> bool:
        """Attained, but resting on at least one unproven control."""
        return self.attained and bool(self.waived_controls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "attained": self.attained,
            "conditional": self.conditional,
            "missing_controls": list(self.missing_controls),
            "blocked_by": list(self.blocked_by),
            "reasons": list(self.reasons),
            "waived_controls": list(self.waived_controls),
            "waiver_ids": list(self.waiver_ids),
        }
