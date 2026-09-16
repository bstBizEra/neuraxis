"""Declared, machine-evaluable envelopes for bounded self-tuning.

ILR-001-DR D-01 splits IL-13:

  * **IL-13a Self-Tuning** is admissible from Band C, but only inside an
    envelope declared in advance and signed by someone other than the
    component it bounds.
  * **IL-13b Self-Modifying** stays in Band G behind full assurance.

The ruling's reasoning is that Option B -- all of IL-13 in Band G -- is right
in principle and unenforceable in practice. Teams doing learning work adjust
thresholds, retry budgets, prompt templates and routing weights; a rule that
forbids it will not be obeyed, it will be reclassified as "configuration" and
done anyway, outside the register. An unenforceable prohibition is worse than
no prohibition, because it moves the activity out of view.

So the line has to be mechanical, not intentional. Three properties make it so:

  1. **Declared in advance.** The envelope names the write targets and the
     numeric limits before the adjustment is requested. A request that names
     no envelope is IL-13b, whatever it calls itself.
  2. **Machine-evaluable.** Every constraint is something this module can
     decide: a target prefix compared component-by-component, a finite numeric
     interval of bounded width. Free text, a target that matches everything, an
     empty limit set and a bound of 1e308 are all refused at load -- the last
     three because a boundary that bounds nothing is permission wearing a
     boundary's name.
  3. **Not self-amended.** The signer may not be the principal the envelope
     bounds. A component that can widen its own envelope has IL-13b under
     another name.

**Two kinds of principal comparison, and why they differ.** The self-signing
check must fail when two names *might* be the same principal, so it uses the
aggressive fold in `normalise_principal` -- every collision there produces a
refusal. The "does this envelope bound you" check and the signer allowlist are
the opposite: a collision there produces an *authorisation*, so they use
`strict_principal`, which normalises form and rejects invisible characters but
never case-folds or strips accents. `agent-cortex` and `agent-cörtex` are
different principals; an earlier cut of this module let the second use the
first's envelope, because it reused a fold whose safety argument only held for
inequality tests.

What this module does not do is stop a write. L0 enforces at write time; this
is the grant-time gate, which decides whether the adjustment is authorised at
all. The two together are the control; either alone is half of it.

**And what it cannot do at all.** `signed_by` is a string in a JSONL file that
the bounded component can also write. Nothing here verifies a signature and
nothing dereferences `manifest_ref`. Populating `authority.envelope_signers`
narrows who may be *named*; it does not make the naming authentic. This control
becomes real when KBS-001 T1 gives the envelope file a kernel write path and
real signing keys -- not merely when the allowlist is filled in.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .errors import EnvelopeError
from .model import has_invisible, normalise_principal, strict_principal, now_utc

__all__ = [
    "MAX_ENVELOPE_TTL_CEILING",
    "MAX_LIMIT_MAGNITUDE",
    "OUT_OF_ENVELOPE",
    "Envelope",
    "EnvelopePolicy",
    "EnvelopeRegister",
    "Limit",
    "scope_fault",
]

#: Marker opening every envelope-path denial reason. Exported so the D-01
#: reversal-trigger audit matches on a constant rather than on prose. It marks
#: every way an adjustment failed its bound -- outside the target, outside a
#: limit, no such envelope, expired, wrong principal -- because all of them are
#: the split being leaned on, which is what the trigger exists to surface.
OUT_OF_ENVELOPE = "out-of-envelope"

#: The register sets no number here. 90 days is borrowed from D-05's waiver
#: bound for consistency, and is a ceiling rather than a default so that a
#: registry can tighten it without being able to declare a perpetual envelope.
MAX_ENVELOPE_TTL_CEILING = timedelta(days=90)

#: `[0, 1e308]` is finite and is the `inf` bypass under another name. A tunable
#: parameter -- a retry budget, a confidence floor, a timeout in milliseconds --
#: does not need a bound wider than this. One that genuinely does is a decision
#: to take deliberately, not to reach by typing more zeroes.
MAX_LIMIT_MAGNITUDE = 1e12

#: Targets that would make the envelope vacuous.
_VACUOUS_TARGETS = frozenset({"*", "**", "/", ".", "", "/*", "**/*"})

#: Characters a path may not contain. `\` because mixing separators makes two
#: spellings of one path; `%` because percent-encoding hides both a separator
#: and a traversal from a component-wise comparison.
_ILLEGAL_PATH_CHARS = ("\\", "%")


def _path_parts(value: str) -> tuple[str, ...] | None:
    """Split a POSIX-style path into components, or None if untrustworthy.

    Returns None for anything a prefix comparison cannot safely decide: a
    traversal component, a mixed separator, percent-encoding, or an invisible
    character. `None` is a refusal, so every such path falls outside every
    envelope.
    """
    if not isinstance(value, str) or has_invisible(value):
        return None
    if any(ch in value for ch in _ILLEGAL_PATH_CHARS):
        return None
    parts = tuple(p for p in value.strip().split("/") if p)
    if any(p in (".", "..") for p in parts):
        # `hippocampus/lessons/../../kernel` starts with `hippocampus/lessons/`
        # and is not under it. Prefix matching cannot see that; refusing the
        # input is cheaper and safer than resolving it.
        return None
    return parts


def scope_fault(scope: str) -> str | None:
    """Why `scope` cannot be compared to a target, or None if it can."""
    if _path_parts(scope) is None:
        return (
            f"{OUT_OF_ENVELOPE}: scope {scope!r} cannot be compared to a declared "
            "target -- it contains a traversal component, a mixed separator, "
            "percent-encoding, or an invisible character"
        )
    return None


def _clean(value: Any, key: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvelopeError(f"{where}: {key!r} must be a non-empty string")
    if has_invisible(value):
        raise EnvelopeError(
            f"{where}: {key!r} contains an invisible or control character; a target "
            "or principal that renders as one string and compares as another is not "
            "machine-evaluable"
        )
    return value.strip()


def _timestamp(value: Any, key: str, where: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise EnvelopeError(f"{where}: {key!r} is not a valid timestamp: {exc}") from exc
    else:
        raise EnvelopeError(f"{where}: {key!r} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        raise EnvelopeError(
            f"{where}: {key!r} carries no timezone; a naive expiry lapses in whatever "
            "zone the reader happens to be in"
        )
    return parsed


@dataclass(frozen=True)
class Limit:
    """A closed numeric interval a tunable parameter may move within."""

    low: float
    high: float

    def __post_init__(self) -> None:
        for name in ("low", "high"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EnvelopeError(f"limit {name} must be a number, got {value!r}")
            value = float(value)
            if not math.isfinite(value):
                # inf and NaN both defeat a comparison: `x <= inf` is always
                # true and every comparison with NaN is false, so either one
                # turns the bound into a formality.
                raise EnvelopeError(f"limit {name} must be finite, got {value!r}")
            if abs(value) > MAX_LIMIT_MAGNITUDE:
                raise EnvelopeError(
                    f"limit {name}={value!r} exceeds the maximum magnitude "
                    f"{MAX_LIMIT_MAGNITUDE:g}. A finite bound this wide is the "
                    "infinity bypass with more zeroes"
                )
            object.__setattr__(self, name, value)
        if self.low > self.high:
            raise EnvelopeError(f"limit low {self.low} exceeds high {self.high}")

    def contains(self, value: float) -> bool:
        return math.isfinite(value) and self.low <= value <= self.high

    def to_list(self) -> list[float]:
        return [self.low, self.high]


@dataclass(frozen=True)
class Envelope:
    """One declared, signed, machine-evaluable bound on self-tuning."""

    id: str
    principal: str
    capability: str
    signed_by: str
    manifest_ref: str
    targets: tuple[str, ...]
    limits: Mapping[str, Limit]
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for key in ("id", "principal", "capability", "signed_by", "manifest_ref"):
            object.__setattr__(
                self, key, _clean(getattr(self, key), key, f"envelope {self.id!r}")
            )
        object.__setattr__(self, "targets", _targets(self.targets, f"envelope {self.id!r}"))
        object.__setattr__(self, "limits", _limits(self.limits, f"envelope {self.id!r}"))
        object.__setattr__(
            self, "issued_at", _timestamp(self.issued_at, "issued_at", f"envelope {self.id!r}")
        )
        object.__setattr__(
            self, "expires_at", _timestamp(self.expires_at, "expires_at", f"envelope {self.id!r}")
        )
        if self.expires_at <= self.issued_at:
            raise EnvelopeError(
                f"envelope {self.id}: expires_at is not after issued_at; an envelope "
                "with no live interval bounds nothing"
            )
        if normalise_principal(self.signed_by) == normalise_principal(self.principal):
            # D-01's second deny, on the AGGRESSIVE fold: here a collision
            # produces a refusal, so folding two names together is the safe
            # direction. `bounds()` below is the opposite case.
            raise EnvelopeError(
                f"envelope {self.id}: signed by the principal it bounds "
                f"({self.principal}). An envelope amended by the component it "
                "constrains is not a constraint"
            )

    @property
    def ttl(self) -> timedelta:
        return self.expires_at - self.issued_at

    def is_active(self, at: datetime) -> bool:
        """Active on [issued_at, expires_at). Declared in advance, expires hard."""
        return self.issued_at <= at < self.expires_at

    def bounds(self, identity: str) -> bool:
        """Whether this envelope constrains `identity`.

        STRICT comparison, not the aggressive fold: a True here authorises, so
        every collision would widen the envelope to a principal it never named.
        """
        return strict_principal(identity) == strict_principal(self.principal)

    def may_bind(self, identity: str) -> bool:
        """Whether this envelope *might* constrain `identity`.

        The mirror of `bounds()`, and deliberately a separate method rather
        than a flag on it. A True here DENIES -- it is the verifier-independence
        question, "does this principal already hold authority over what it is
        being asked to verify?" -- so every collision must fail closed, which
        means the aggressive fold.

        Reusing `bounds()` for this would be the same mistake the v0.9.0 review
        found, in the same file: a fold whose safety argument holds in one
        direction reused in the other. The two questions look identical and
        their safe answers are opposite.
        """
        return normalise_principal(identity) == normalise_principal(self.principal)

    def covers_target(self, scope: str) -> bool:
        """True if `scope` sits at or under one of the declared targets.

        Component-wise, never a bare `startswith`: `hippocampus/lessons` must
        not cover `hippocampus/lessons-archive`, and must not cover
        `hippocampus/lessons/../../kernel` either.
        """
        parts = _path_parts(scope)
        if parts is None:
            return False
        for target in self.targets:
            stem = _path_parts(target)
            if stem and parts[: len(stem)] == stem:
                return True
        return False

    def violations(self, adjustments: Mapping[str, float]) -> tuple[str, ...]:
        """Every reason these adjustments fall outside the declared limits."""
        out: list[str] = []
        for key in sorted(adjustments):
            raw = adjustments[key]
            limit = self.limits.get(key)
            if limit is None:
                out.append(
                    f"{OUT_OF_ENVELOPE}: {key!r} is not a parameter {self.id} declares "
                    f"(declared: {', '.join(sorted(self.limits)) or 'none'})"
                )
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                out.append(
                    f"{OUT_OF_ENVELOPE}: {key!r} is {raw!r}, which is not a number; "
                    "a bound that cannot be compared is not a bound"
                )
                continue
            if not limit.contains(float(raw)):
                out.append(
                    f"{OUT_OF_ENVELOPE}: {key}={raw} is outside the declared "
                    f"[{limit.low:g}, {limit.high:g}] in {self.id}"
                )
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "principal": self.principal,
            "capability": self.capability,
            "signed_by": self.signed_by,
            "manifest_ref": self.manifest_ref,
            "targets": list(self.targets),
            "limits": {k: v.to_list() for k, v in sorted(self.limits.items())},
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, where: str = "envelope") -> "Envelope":
        if not isinstance(payload, Mapping):
            raise EnvelopeError(f"{where}: envelope record must be a JSON object")
        known = {
            "id", "principal", "capability", "signed_by", "manifest_ref",
            "targets", "limits", "issued_at", "expires_at",
        }
        unknown = sorted(set(payload) - known)
        if unknown:
            # A typo'd `limits_` would otherwise load as an envelope with no
            # numeric bounds at all, which is the widest possible envelope
            # arriving through a spelling mistake.
            raise EnvelopeError(f"{where}: unknown envelope field(s) {', '.join(unknown)}")
        return cls(
            id=payload.get("id"),
            principal=payload.get("principal"),
            capability=payload.get("capability"),
            signed_by=payload.get("signed_by"),
            manifest_ref=payload.get("manifest_ref"),
            targets=payload.get("targets"),
            limits=payload.get("limits"),
            issued_at=payload.get("issued_at"),
            expires_at=payload.get("expires_at"),
        )


def _targets(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise EnvelopeError(
            f"{where}: 'targets' must be a list of write-target prefixes. A bare "
            "string is not a list: membership on it is substring matching"
        )
    out: list[str] = []
    for item in value:
        target = _clean(item, "targets entry", where)
        if target.strip("/") in _VACUOUS_TARGETS or not target.strip("/"):
            raise EnvelopeError(
                f"{where}: target {item!r} matches everything. An envelope that "
                "covers the whole namespace is permission wearing a boundary's name"
            )
        if not _path_parts(target):
            raise EnvelopeError(
                f"{where}: target {item!r} is not a comparable path -- it contains a "
                "traversal component, a mixed separator, or percent-encoding"
            )
        out.append(target)
    if not out:
        raise EnvelopeError(
            f"{where}: 'targets' is empty. An envelope with no declared target is "
            "not machine-evaluable, and an unevaluable envelope is IL-13b"
        )
    if len(set(out)) != len(out):
        raise EnvelopeError(f"{where}: 'targets' contains duplicates")
    return tuple(out)


def _limits(value: Any, where: str) -> Mapping[str, Limit]:
    if value is None or not isinstance(value, Mapping):
        raise EnvelopeError(
            f"{where}: 'limits' must be a mapping of parameter to [low, high]"
        )
    out: dict[str, Limit] = {}
    for key, bound in value.items():
        name = _clean(key, "limits key", where)
        if isinstance(bound, Limit):
            out[name] = bound
            continue
        if not isinstance(bound, (list, tuple)) or len(bound) != 2:
            raise EnvelopeError(
                f"{where}: limit {name!r} must be a two-element [low, high]; "
                f"got {bound!r}. A constraint this module cannot evaluate is prose"
            )
        out[name] = Limit(bound[0], bound[1])
    if not out:
        # Same rule as an empty target list, and for the same reason: an
        # envelope declaring no parameter bounds no parameter, while reporting
        # in every verdict as a bound.
        raise EnvelopeError(
            f"{where}: 'limits' is empty. An envelope that declares no parameter "
            "bounds no adjustment, and is IL-13b with a record attached"
        )
    return out


@dataclass(frozen=True)
class EnvelopePolicy:
    """Registry-supplied bounds on the envelope path."""

    signers: frozenset[str] = frozenset()
    max_ttl: timedelta = MAX_ENVELOPE_TTL_CEILING

    def __post_init__(self) -> None:
        for signer in self.signers:
            if not isinstance(signer, str) or not signer.strip():
                raise EnvelopeError(f"envelope signer {signer!r} is not a principal name")
        object.__setattr__(self, "signers", frozenset(self.signers))
        if not isinstance(self.max_ttl, timedelta):
            raise EnvelopeError(f"envelope max_ttl must be a timedelta, got {self.max_ttl!r}")
        if self.max_ttl <= timedelta(0):
            raise EnvelopeError(f"envelope max_ttl must be positive, got {self.max_ttl}")
        object.__setattr__(self, "max_ttl", min(self.max_ttl, MAX_ENVELOPE_TTL_CEILING))

    @property
    def signers_restricted(self) -> bool:
        return bool(self.signers)

    def signer_permitted(self, signed_by: str) -> bool:
        """STRICT comparison: a collision here authorises, so it must not fold."""
        if not self.signers_restricted:
            return True
        return strict_principal(signed_by) in {strict_principal(s) for s in self.signers}


class EnvelopeRegister:
    """A validated set of envelopes, evaluated against a policy."""

    def __init__(
        self,
        envelopes: Iterable[Envelope] = (),
        *,
        policy: EnvelopePolicy | None = None,
        known_capabilities: Iterable[str] | None = None,
    ) -> None:
        self.policy = policy or EnvelopePolicy()
        self._envelopes: tuple[Envelope, ...] = tuple(
            sorted(envelopes, key=lambda e: (e.issued_at, e.id))
        )
        self._by_id: dict[str, Envelope] = {}
        capabilities = set(known_capabilities) if known_capabilities is not None else None
        for env in self._envelopes:
            if env.id in self._by_id:
                raise EnvelopeError(f"duplicate envelope id {env.id!r}")
            self._by_id[env.id] = env
            if capabilities is not None and env.capability not in capabilities:
                raise EnvelopeError(
                    f"envelope {env.id}: {env.capability} is not a defined capability"
                )
            fault = self.policy_fault(env)
            if fault is not None:
                raise EnvelopeError(f"envelope {env.id}: {fault}")

    def policy_fault(self, envelope: Envelope) -> str | None:
        """Why `envelope` breaches the policy, or None.

        Exposed so the gate can re-check at use time. Construction-time
        validation alone is not enough: a register built with the default
        policy and handed to a gate whose registry tightened the bounds would
        otherwise carry envelopes that registry would have refused.
        """
        if envelope.ttl > self.policy.max_ttl:
            return (
                f"TTL {envelope.ttl} exceeds the maximum {self.policy.max_ttl}. An "
                "envelope declared for longer than a mission is a standing grant"
            )
        if not self.policy.signer_permitted(envelope.signed_by):
            return (
                f"{envelope.signed_by!r} is not a declared envelope signer "
                f"({', '.join(sorted(self.policy.signers))})"
            )
        return None

    # ---- construction --------------------------------------------------

    @classmethod
    def empty(cls, policy: EnvelopePolicy | None = None) -> "EnvelopeRegister":
        return cls((), policy=policy)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        policy: EnvelopePolicy | None = None,
        known_capabilities: Iterable[str] | None = None,
    ) -> "EnvelopeRegister":
        path = Path(path)
        if not path.is_file():
            return cls((), policy=policy, known_capabilities=known_capabilities)
        records: list[Envelope] = []
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8-sig").split("\n"), start=1
        ):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            where = f"{path}:{lineno}"
            try:
                payload = json.loads(line)
            except ValueError as exc:
                raise EnvelopeError(f"{where}: malformed JSON: {exc}") from exc
            records.append(Envelope.from_dict(payload, where=where))
        return cls(records, policy=policy, known_capabilities=known_capabilities)

    @classmethod
    def for_registry(
        cls, registry: Any, path: str | Path | None = None, envelopes: Iterable[Envelope] = ()
    ) -> "EnvelopeRegister":
        kwargs = {
            "policy": registry.envelope_policy,
            "known_capabilities": registry.capabilities.keys(),
        }
        if path is not None:
            return cls.from_file(path, **kwargs)
        return cls(envelopes, **kwargs)

    # ---- evaluation ----------------------------------------------------

    def get(self, envelope_id: str) -> Envelope | None:
        return self._by_id.get(envelope_id)

    def active(self, at: datetime | None = None) -> tuple[Envelope, ...]:
        at = at or now_utc()
        return tuple(e for e in self._envelopes if e.is_active(at))

    def authority_over(
        self, identity: str, scope: str, *, at: datetime | None = None
    ) -> tuple[Envelope, ...]:
        """Active envelopes that may give `identity` write authority over `scope`.

        This is the lookup behind W9's third clause -- "deny if the verifying
        principal shares the performing principal's envelope". A verifier that
        holds a declared bound over the very target being changed is not an
        independent verifier; it is a second party with a stake in the outcome.

        Two deliberate asymmetries with the authorising path:

        * principals are matched with `may_bind`, the aggressive fold, because
          a match here denies;
        * a scope that cannot be compared to a target -- a traversal component,
          a mixed separator, an invisible character -- returns **every** active
          envelope binding the identity rather than none. On the authorising
          path an uncomparable scope is outside every envelope; here that same
          answer would read as "this verifier has no authority", which is a
          conclusion nobody is entitled to draw from a string nobody can parse.
        """
        at = at or now_utc()
        binding = tuple(e for e in self.active(at) if e.may_bind(identity))
        if not binding:
            return ()
        if _path_parts(scope) is None:
            return binding
        return tuple(e for e in binding if e.covers_target(scope))

    @staticmethod
    def append_to_file(path: str | Path, envelope: Envelope) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope.to_dict(), sort_keys=True) + "\n")

    def __iter__(self) -> Iterator[Envelope]:
        return iter(self._envelopes)

    def __len__(self) -> int:
        return len(self._envelopes)
