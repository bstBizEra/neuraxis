"""The decision register as versioned config (ILR-001-DR W8).

The register document rules on six structural questions and, with its addendum,
a seventh. Every ruling carries a reversal trigger, and the register says why:
*a ruling with no reversal condition is dogma.*

But a reversal trigger written in prose fires only if somebody remembers it.
W8's ask is that a trigger firing be **detectable rather than remembered**, and
that is what this module is for.

Two invariants make the file worth having rather than being a YAML transcript
of the document:

**Every ruling names the code that enforces it, and that symbol must import.**
Rename `NON_COMPENSABLE_FLOOR` and this file stops loading. It is the only
mechanism that keeps a ruling attached to its implementation: a document can
describe an enforcement point that was deleted three releases ago and read
exactly as convincingly as one that exists.

**Every reversal trigger is either detectable or owned.** A trigger with a
detector fires on its own. A trigger without one must name a person and a
review cadence, because some triggers genuinely cannot be watched by a
machine -- *an external party cites an ordinal level back to BST in writing*
arrives in somebody's inbox, not in the evidence sink. What the file refuses is
a trigger that is neither, which is a trigger nobody will notice.

**This file is not kernel, and carefully so.** Nothing in it bounds anything.
The enforcement clauses quoted in the register are descriptive; the
authoritative ones are constants in code, because a bound that exists to
constrain config cannot live in config (ADR 0006). Putting the non-compensable
floor in this YAML would re-create precisely the bug that ADR fixed.
"""

from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .errors import NeuraxisError
from .model import now_utc

__all__ = [
    "ARMED",
    "CLEAR",
    "SEALED",
    "UNRUN",
    "WATCHED",
    "DecisionRegister",
    "Enforcement",
    "RegisterError",
    "Reversal",
    "Ruling",
    "RulingStatus",
    "TriggerState",
    "load_register",
]

DEFAULT_REGISTER = Path(__file__).with_name("config") / "register.yaml"
DEFAULT_TIMEOUT = 60.0

#: A trigger's state. `WATCHED` is not a weaker `CLEAR` -- it means no machine
#: looked, and the named owner is the entire control.
ARMED = "ARMED"
CLEAR = "CLEAR"
WATCHED = "WATCHED"
UNRUN = "NOT RUN"
#: A trigger whose own structure prevents it firing. Distinct from CLEAR --
#: CLEAR means a detector looked and saw nothing; SEALED means nothing looked
#: because nothing could fire. It used to report CLEAR and appear in neither
#: the armed nor the watched list, which made deleting `owner`/`review` and
#: writing `detector: {kind: by_construction, why: "."}` the cheapest way to
#: remove an inconvenient trigger from every list in the report.
SEALED = "SEALED"

_DETECTOR_KINDS = ("command", "by_construction")

#: A `why` shorter than this, or matching one of these, is not a reason.
_MIN_WHY = 40
_EMPTY_WHY = frozenset({"", "todo", "n/a", "na", "none", "obvious", "by construction"})

#: Run this package's CLI in this interpreter. Not through PATH, and not
#: through an environment variable.
_CLI_SHIM = "import sys; from neuraxis.cli import main; sys.exit(main(sys.argv[1:]))"


def _detector_argv(run: Sequence[str]) -> list[str]:
    """Resolve a detector's command.

    A detector named `neuraxis` asks THIS package a question, so it runs in
    THIS interpreter. Nothing about it is resolved from the environment or from
    PATH.

    The previous version resolved `NEURAXIS_BIN` first, then PATH, then the
    interpreter -- reasoning that a PATH miss is not evidence about the
    register and should not report a trigger armed. That reasoning is sound for
    avoiding a false ARM and was applied to a mechanism that manufactures a
    false CLEAR: `NEURAXIS_BIN=/bin/true`, or a two-line `exit 0` script named
    `neuraxis` earlier on PATH, turned every detector CLEAR. In a fail-closed
    system a false CLEAR is strictly worse than a false ARM, and this is the
    module that watches D-07 reproducing D-07's own substitutability problem.

    A detector naming any other command runs as given; that command is a third
    party and is the caller's business.
    """
    argv = [str(part) for part in run]
    if not argv or argv[0] != "neuraxis":
        return argv
    return [sys.executable, "-c", _CLI_SHIM, *argv[1:]]


class RegisterError(NeuraxisError):
    """The register could not be loaded, or violates one of its invariants."""


class _StrictLoader(yaml.SafeLoader):
    """Refuses a duplicate mapping key; PyYAML takes the last one silently."""


def _no_duplicate_keys(loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise RegisterError(
                f"duplicate key {key!r} at line {key_node.start_mark.line + 1}; "
                "the later one would silently win"
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.construct_mapping = _no_duplicate_keys  # type: ignore[method-assign]


def _resolve(ref: str) -> Any:
    """Import `module:attr` or `module:Class.attr`, or raise."""
    module_name, sep, attr = ref.partition(":")
    if not sep or not attr.strip():
        raise RegisterError(
            f"{ref!r} is not a symbol reference; use module:name or module:Class.name"
        )
    if module_name != "neuraxis" and not module_name.startswith("neuraxis."):
        # `importlib.import_module` on a string from a config file runs that
        # module. `neuraxis register` looks like a read-only status command and
        # was the only config in the package that executed code.
        raise RegisterError(
            f"{ref}: a ruling's enforcement point must be inside this package. "
            "Importing a module named in a config file runs it"
        )
    try:
        obj: Any = importlib.import_module(module_name)
    except ImportError as exc:
        raise RegisterError(f"{ref}: no module {module_name} ({exc})") from None
    walked = module_name
    for part in attr.split("."):
        # `getattr_static` rather than `hasattr` + `getattr`: the pair ran every
        # descriptor twice, and a module-level `__getattr__` -- the standard
        # deprecation-shim pattern -- satisfied any name at all, which would
        # have made this whole check vacuous the day one was added.
        try:
            inspect.getattr_static(obj, part)
        except AttributeError:
            raise RegisterError(
                f"{ref}: {walked} has no {part!r}. The enforcement point named by this "
                "ruling does not exist -- either it was renamed and the ruling is now "
                "unattached, or it was never built"
            ) from None
        obj = inspect.getattr_static(obj, part)
        walked = f"{walked}.{part}"
    return obj


@dataclass(frozen=True)
class Enforcement:
    """Where a ruling is enforced, and the proof that it still is."""

    #: `module:name`, verified to import at load.
    symbol: str = ""
    #: A capability the shipped registry must carry.
    capability: str = ""
    note: str = ""

    def describe(self) -> str:
        return self.symbol or f"capability {self.capability}"


@dataclass(frozen=True)
class Reversal:
    """The condition under which a ruling is wrong, and who or what watches it."""

    trigger: str
    fallback: str = ""
    detector_kind: str = ""
    run: tuple[str, ...] = ()
    armed_on_exit: int | None = None
    why: str = ""
    owner: str = ""
    review: str = ""
    note: str = ""
    divergence: str = ""

    @property
    def detectable(self) -> bool:
        return bool(self.detector_kind)


@dataclass(frozen=True)
class Ruling:
    id: str
    title: str
    ruling: str
    question: str = ""
    score: float | None = None
    amends_draft: bool = False
    folded_from: str = ""
    enforcement: tuple[Enforcement, ...] = ()
    reversal: Reversal | None = None


@dataclass(frozen=True)
class TriggerState:
    ruling: str
    state: str
    detail: str

    @property
    def armed(self) -> bool:
        return self.state == ARMED

    def to_dict(self) -> dict[str, Any]:
        return {"ruling": self.ruling, "state": self.state, "detail": self.detail}


@dataclass(frozen=True)
class RulingStatus:
    ruling: Ruling
    enforced: bool
    missing: tuple[str, ...]
    trigger: TriggerState
    #: True when no capability list was supplied, so the capability half of
    #: `enforced` could not be evaluated at all.
    unchecked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.ruling.id,
            "title": self.ruling.title,
            "ruling": self.ruling.ruling,
            "score": self.ruling.score,
            "amends_draft": self.ruling.amends_draft,
            "enforcement": [e.describe() for e in self.ruling.enforcement],
            "enforced": self.enforced,
            "unchecked": self.unchecked,
            "missing": list(self.missing),
            "trigger": self.trigger.to_dict(),
        }


@dataclass(frozen=True)
class RegisterReport:
    register: str
    revision: str
    evaluated_at: datetime
    rulings: tuple[RulingStatus, ...] = ()

    @property
    def armed(self) -> tuple[RulingStatus, ...]:
        return tuple(r for r in self.rulings if r.trigger.armed)

    @property
    def unrun(self) -> tuple[RulingStatus, ...]:
        """Detectors nobody ran. Not clear; nobody looked."""
        return tuple(r for r in self.rulings if r.trigger.state == UNRUN)

    @property
    def sealed(self) -> tuple[RulingStatus, ...]:
        return tuple(r for r in self.rulings if r.trigger.state == SEALED)

    @property
    def watched(self) -> tuple[RulingStatus, ...]:
        """Triggers no machine can see. The named owner is the whole control."""
        return tuple(r for r in self.rulings if r.trigger.state == WATCHED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "register": self.register,
            "revision": self.revision,
            "evaluated_at": self.evaluated_at.isoformat(),
            "armed": [r.ruling.id for r in self.armed],
            "watched": [r.ruling.id for r in self.watched],
            "sealed": [r.ruling.id for r in self.sealed],
            "not_run": [r.ruling.id for r in self.unrun],
            "rulings": [r.to_dict() for r in self.rulings],
        }


@dataclass(frozen=True)
class DecisionRegister:
    name: str
    revision: str
    source: str
    path: Path | None
    rulings: Mapping[str, Ruling]
    criteria: Mapping[str, Any]

    def resolve(
        self,
        *,
        run_detectors: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        capabilities: Sequence[str] = (),
        at: datetime | None = None,
    ) -> RegisterReport:
        at = at or now_utc()
        known = set(capabilities)
        statuses: list[RulingStatus] = []
        for ruling in self.rulings.values():
            wanted = tuple(e.capability for e in ruling.enforcement if e.capability)
            if wanted and not known:
                # `and known` used to short-circuit on an empty set, so the
                # DEFAULT call -- no capability list, which is what a caller
                # whose registry failed to load passes -- reported every ruling
                # enforced. Supplying nothing read as "everything present"
                # while supplying the WRONG list read as missing: the failure
                # mode exactly backwards. Not recognised must never resolve to
                # no objection.
                missing = wanted
                unchecked = True
            else:
                missing = tuple(c for c in wanted if c not in known)
                unchecked = False
            statuses.append(
                RulingStatus(
                    ruling=ruling,
                    enforced=not missing and not unchecked,
                    missing=missing,
                    unchecked=unchecked,
                    trigger=self._trigger(ruling, run_detectors, timeout),
                )
            )
        return RegisterReport(
            register=self.name, revision=self.revision, evaluated_at=at,
            rulings=tuple(statuses),
        )

    @staticmethod
    def _trigger(ruling: Ruling, run: bool, timeout: float) -> TriggerState:
        rev = ruling.reversal
        if rev is None:
            return TriggerState(ruling.id, WATCHED, "no reversal condition recorded")
        if not rev.detectable:
            return TriggerState(
                ruling.id, WATCHED,
                f"watched by {rev.owner} ({rev.review or 'no cadence'}) - no machine sees this one",
            )
        if rev.detector_kind == "by_construction":
            return TriggerState(ruling.id, SEALED, rev.why)
        if not run:
            return TriggerState(
                ruling.id, UNRUN, "pass --check to run the detector; until then nobody looked"
            )
        try:
            argv = _detector_argv(rev.run)
        except RegisterError as exc:
            return TriggerState(ruling.id, ARMED, f"detector could not be resolved: {exc}")
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout, check=False
            )
        except FileNotFoundError:
            return TriggerState(ruling.id, ARMED, f"{argv[0]!r} not found; the detector is gone")
        except subprocess.TimeoutExpired:
            return TriggerState(ruling.id, ARMED, f"detector timed out after {timeout:g}s")
        except OSError as exc:
            return TriggerState(ruling.id, ARMED, f"detector could not run: {exc}")
        if completed.returncode == rev.armed_on_exit:
            first = (completed.stdout or completed.stderr or "").strip().splitlines()
            return TriggerState(
                ruling.id, ARMED,
                f"exit {completed.returncode}" + (f": {first[0][:160]}" if first else ""),
            )
        if completed.returncode == 0:
            return TriggerState(ruling.id, CLEAR, "detector exited 0")
        # Neither clear nor the armed code. A detector that failed for some
        # third reason has not reported "clear", and reading it as clear is the
        # unrecognised-exit-code failure in a new place.
        return TriggerState(
            ruling.id, ARMED,
            f"detector exited {completed.returncode}, which is neither 0 nor the armed code "
            f"{rev.armed_on_exit}; a detector that cannot answer has not answered",
        )


# ---- loading -----------------------------------------------------------


def _enforcement(raw: Any, rid: str) -> Enforcement:
    if not isinstance(raw, Mapping):
        raise RegisterError(f"{rid}: an enforcement entry must be a mapping")
    symbol = str(raw.get("symbol", "")).strip()
    capability = str(raw.get("capability", "")).strip()
    if bool(symbol) == bool(capability):
        raise RegisterError(
            f"{rid}: an enforcement entry names exactly one of `symbol` or `capability`"
        )
    if symbol:
        _resolve(symbol)
    return Enforcement(symbol=symbol, capability=capability, note=str(raw.get("note", "")).strip())


def _reversal(raw: Any, rid: str) -> Reversal:
    if not isinstance(raw, Mapping):
        raise RegisterError(f"{rid}: `reversal` must be a mapping")
    trigger = str(raw.get("trigger", "")).strip()
    if not trigger:
        raise RegisterError(
            f"{rid}: no reversal trigger. A ruling with no stated way to be wrong is dogma"
        )
    detector = raw.get("detector")
    owner = str(raw.get("owner", "")).strip()
    review = str(raw.get("review", "")).strip()

    if detector is None:
        # The invariant W8 exists for.
        if not owner or not review:
            raise RegisterError(
                f"{rid}: the reversal trigger has no detector and no owner with a review "
                "cadence. A trigger that is neither detectable nor owned is remembered, "
                "and a remembered trigger is one nobody notices firing"
            )
        return Reversal(
            trigger=trigger, fallback=str(raw.get("fallback", "")).strip(),
            owner=owner, review=review, note=str(raw.get("note", "")).strip(),
            divergence=str(raw.get("divergence", "")).strip(),
        )

    if not isinstance(detector, Mapping):
        raise RegisterError(f"{rid}: `detector` must be a mapping")
    kind = str(detector.get("kind", "")).strip()
    if kind not in _DETECTOR_KINDS:
        raise RegisterError(
            f"{rid}: detector kind {kind!r} is not one of {', '.join(_DETECTOR_KINDS)}"
        )
    run = detector.get("run") or ()
    if isinstance(run, (str, bytes)):
        raise RegisterError(f"{rid}: detector `run` is argv, not a command line")
    armed = detector.get("armed_on_exit")
    if kind == "command":
        if not run:
            raise RegisterError(f"{rid}: a command detector with no command detects nothing")
        if not isinstance(armed, int) or isinstance(armed, bool):
            raise RegisterError(
                f"{rid}: a command detector must say which exit code means ARMED"
            )
        if armed == 0:
            raise RegisterError(
                f"{rid}: armed_on_exit 0 would read every successful run as a fired trigger"
            )
    if kind == "by_construction":
        why = str(detector.get("why", "")).strip()
        if len(why) < _MIN_WHY or why.lower().rstrip(".") in _EMPTY_WHY:
            # `why: "."` and `why: "TODO"` both passed a non-empty check, and a
            # sealed trigger appeared in neither the armed nor the watched list.
            raise RegisterError(
                f"{rid}: a by_construction detector must say why the trigger cannot "
                "fire, in a sentence. Otherwise it is indistinguishable from a "
                "trigger nobody wired, and sealing one is the cheapest way to make "
                "it disappear from every list"
            )
        if not owner or not review:
            raise RegisterError(
                f"{rid}: a by_construction trigger still names an owner and a review "
                "cadence. The claim that it cannot fire is itself a claim, and "
                "somebody has to be the one who notices it stopped being true"
            )
    return Reversal(
        trigger=trigger, fallback=str(raw.get("fallback", "")).strip(),
        owner=owner, review=review,
        detector_kind=kind, run=tuple(str(p) for p in run),
        armed_on_exit=armed if isinstance(armed, int) and not isinstance(armed, bool) else None,
        why=str(detector.get("why", "")).strip(),
        note=str(raw.get("note", "")).strip(),
        divergence=str(raw.get("divergence", "")).strip(),
    )


def load_register(path: str | Path | None = None) -> DecisionRegister:
    """Load and fully validate the register. No partial register, ever."""
    resolved = Path(path) if path else DEFAULT_REGISTER
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RegisterError(f"could not read {resolved}: {exc}") from None
    try:
        data = yaml.load(text, Loader=_StrictLoader)
    except RegisterError:
        raise
    except yaml.YAMLError as exc:
        raise RegisterError(f"{resolved}: not valid YAML: {exc}") from None
    if not isinstance(data, Mapping):
        raise RegisterError(f"{resolved}: the register must be a mapping")

    raw_rulings = data.get("rulings") or {}
    if not isinstance(raw_rulings, Mapping) or not raw_rulings:
        raise RegisterError(f"{resolved}: `rulings` must be a non-empty mapping")

    rulings: dict[str, Ruling] = {}
    for rid, raw in raw_rulings.items():
        rid = str(rid).strip()
        if not isinstance(raw, Mapping):
            raise RegisterError(f"{rid}: a ruling must be a mapping")
        decision = str(raw.get("ruling", "")).strip()
        if not decision:
            raise RegisterError(f"{rid}: a ruling with no ruling is a question")
        enforcement = tuple(_enforcement(e, rid) for e in (raw.get("enforcement") or ()))
        if not enforcement:
            raise RegisterError(
                f"{rid}: no enforcement point. The register's own words: a ruling with no "
                "enforcement point is an opinion that loses to schedule pressure"
            )
        score = raw.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
            raise RegisterError(f"{rid}: score must be a number or null, got {score!r}")
        rulings[rid] = Ruling(
            id=rid,
            title=str(raw.get("title", "")).strip() or rid,
            ruling=decision,
            question=str(raw.get("question", "")).strip(),
            score=float(score) if score is not None else None,
            amends_draft=bool(raw.get("amends_draft", False)),
            folded_from=str(raw.get("folded_from", "")).strip(),
            enforcement=enforcement,
            reversal=_reversal(raw.get("reversal"), rid) if raw.get("reversal") else None,
        )
        if rulings[rid].reversal is None:
            raise RegisterError(
                f"{rid}: no reversal condition. A ruling with no reversal condition is dogma"
            )

    return DecisionRegister(
        name=str(data.get("register", "")).strip() or resolved.stem,
        revision=str(data.get("revision", "")).strip(),
        source=str(data.get("source", "")).strip(),
        path=resolved,
        rulings=rulings,
        criteria=dict(data.get("criteria") or {}),
    )
