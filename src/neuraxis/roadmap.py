"""The build sequence as a dependency graph, resolved against the live gate.

A roadmap written as prose is a plan somebody has to interpret, and under
schedule pressure "blocked on T1" interprets into "we will do T1 after". The
register already made this move once -- ILR-001-DR D-02 replaced the IL ladder
with a banded DAG, because nobody can certify "we are at level 22" and because
a numbered list is read as a permission to proceed down it. This applies the
same correction to the build sequence.

Three properties carry the weight:

**Readiness is computed, not declared.** An item's `state` is a claim a human
typed. Its readiness comes from the same resolver the gate runs on: band
attainment from the registry and the attestation store, control freshness from
the same windows, item dependencies from this file. Nothing here can report an
item ready because someone edited a status column.

**A shipped item whose gates are unsatisfied is a contradiction**, and is
reported as one rather than as green. That is the shape of "the Band C work
shipped while Band C was blocked", which is the failure the whole framework
exists to catch, occurring in the plan instead of in the system.

**An unevaluable gate blocks.** An external dependency nobody owns, an unknown
band, a gate kind this version does not recognise: all BLOCKED, never READY.
This is the same rule as the caller contract's unrecognised exit code, for the
same reason -- in a governance tool, "not recognised" must never resolve to
"no objection".

What this file is not: it is **not kernel**. Nothing in the roadmap licenses a
capability, opens a band or waives a control, so changing it is a plan change
and `neuraxis drift` does not cover it. The moment a roadmap could grant
something it would need to be kernel, and the fact that it cannot is what keeps
it cheap to edit.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .attestation import AttestationStore
from .errors import NeuraxisError
from .model import now_utc
from .registry import Registry
from .resolver import BandResolver

__all__ = [
    "GATE_KINDS",
    "ITEM_STATES",
    "Gate",
    "GateResult",
    "ItemReadiness",
    "Roadmap",
    "RoadmapError",
    "RoadmapItem",
    "RoadmapReport",
    "load_roadmap",
]

#: Readiness verdicts. `UNKNOWN` is not a third state between the two -- it is
#: BLOCKED with the reason "nobody could tell", and it is surfaced separately
#: only so the blocker can be chased.
READY = "READY"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

#: Gate kinds this version can evaluate. An unrecognised kind is UNKNOWN, so a
#: gate added by a newer roadmap file blocks an older tool rather than
#: vanishing from it.
GATE_KINDS = ("band_attained", "control_attested", "item", "external", "command")

#: `state` is a claim about work, not about readiness.
ITEM_STATES = ("planned", "in-progress", "partial", "shipped", "blocked", "deferred")

#: States that assert the work is done. A gate unsatisfied under one of these
#: is a contradiction.
_DONE_STATES = frozenset({"shipped"})

DEFAULT_ROADMAP = Path(__file__).with_name("config") / "roadmap.yaml"
DEFAULT_COMMAND_TIMEOUT = 60.0


class RoadmapError(NeuraxisError):
    """The roadmap could not be loaded, or violates one of its invariants."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses a duplicate mapping key.

    PyYAML takes the last one silently. In this file that means an item can
    carry `gates: []` and a real `gates:` block, and the empty one disappears --
    an item reporting READY because a key was written twice. The registry
    loader makes the same refusal for the same reason.
    """


def _no_duplicate_keys(loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise RoadmapError(
                f"duplicate key {key!r} at line {key_node.start_mark.line + 1}; "
                "the later one would silently win and the earlier one would vanish"
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.construct_mapping = _no_duplicate_keys  # type: ignore[method-assign]


@dataclass(frozen=True)
class Gate:
    """One condition an item waits on."""

    kind: str
    id: str = ""
    run: tuple[str, ...] = ()

    def describe(self) -> str:
        if self.kind == "command":
            return f"command `{' '.join(self.run)}`"
        return f"{self.kind} {self.id}"


@dataclass(frozen=True)
class External:
    """A dependency owned by someone else."""

    id: str
    title: str
    owner: str
    attained: bool
    blocks_because: str = ""
    note: str = ""
    verify: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoadmapItem:
    id: str
    title: str
    state: str
    owner: str
    gates: tuple[Gate, ...] = ()
    score: float | None = None
    register_ref: str = ""
    shipped_in: tuple[str, ...] = ()
    remaining: tuple[str, ...] = ()
    note: str = ""
    acceptance: tuple[Mapping[str, Any], ...] = ()
    #: Why this item legitimately waits on nothing. Required for an item with
    #: no gates, so that emptiness is a statement rather than a typo.
    ungated_because: str = ""

    @property
    def claims_done(self) -> bool:
        return self.state in _DONE_STATES

    @property
    def has_shipped(self) -> bool:
        """Some of this item's work is claimed to be in the product already."""
        return bool(self.shipped_in) or self.state in ("shipped", "partial")

    @property
    def acceptance_commands(self) -> tuple[tuple[str, ...], ...]:
        return tuple(
            tuple(str(part) for part in (entry.get("run") or ()))
            for entry in self.acceptance
            if isinstance(entry, Mapping) and entry.get("run")
        )


@dataclass(frozen=True)
class GateResult:
    gate: Gate
    verdict: str
    detail: str

    @property
    def satisfied(self) -> bool:
        return self.verdict == READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.gate.kind,
            "id": self.gate.id or None,
            "verdict": self.verdict,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ItemReadiness:
    item: RoadmapItem
    verdict: str
    gates: tuple[GateResult, ...] = ()
    contradiction: str = ""
    #: Results of the item's acceptance commands, when they were run. An
    #: acceptance that is never executed is a claim, which is what this whole
    #: file exists to stop the roadmap being made of.
    acceptance: tuple[GateResult, ...] = ()

    @property
    def actionable(self) -> bool:
        """Ready to work on: every gate satisfied, and not already finished."""
        return self.verdict == READY and not self.item.claims_done

    @property
    def blockers(self) -> tuple[GateResult, ...]:
        return tuple(g for g in self.gates if not g.satisfied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.item.id,
            "title": self.item.title,
            "state": self.item.state,
            "owner": self.item.owner,
            "score": self.item.score,
            "verdict": self.verdict,
            "actionable": self.actionable,
            "contradiction": self.contradiction or None,
            "gates": [g.to_dict() for g in self.gates],
            "blockers": [g.gate.describe() for g in self.blockers],
            "acceptance": [g.to_dict() for g in self.acceptance],
        }


@dataclass(frozen=True)
class RoadmapReport:
    roadmap: str
    evaluated_at: datetime
    items: tuple[ItemReadiness, ...] = ()
    freeze_in_force: bool | None = None
    freeze_reasons: tuple[str, ...] = ()
    contradictions: tuple[ItemReadiness, ...] = ()

    @property
    def actionable(self) -> tuple[ItemReadiness, ...]:
        """What can be worked on now, highest register score first.

        Unscored items sort last rather than first: an item with no score was
        never weighed against the others, and putting it at the top of a work
        queue would give it a priority nobody assigned it.
        """
        ready = [r for r in self.items if r.actionable]
        return tuple(sorted(ready, key=lambda r: (r.item.score is None, -(r.item.score or 0.0))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "roadmap": self.roadmap,
            "evaluated_at": self.evaluated_at.isoformat(),
            "freeze_in_force": self.freeze_in_force,
            "freeze_reasons": list(self.freeze_reasons),
            "actionable": [r.item.id for r in self.actionable],
            "contradictions": [r.item.id for r in self.contradictions],
            "items": [r.to_dict() for r in self.items],
        }


# ---- loading -----------------------------------------------------------


#: Every key each block may carry. A key outside the set is a load failure,
#: not an ignored line: `gatez:`, `blocked_by:`, `runs:` and `score: true` were
#: all silently accepted, and the first two turned a blocked item into the top
#: of the work queue.
_ITEM_KEYS = frozenset({
    "id", "title", "state", "owner", "gates", "score", "register_ref",
    "shipped_in", "remaining", "note", "acceptance", "ungated_because",
})
_GATE_KEYS = frozenset({"kind", "id", "run", "armed_on_exit"})
_EXTERNAL_KEYS = frozenset({
    "title", "owner", "attained", "blocks_because", "note", "verify",
})
_ACCEPTANCE_KEYS = frozenset({"kind", "run", "proves"})
_FREEZE_KEYS = frozenset({
    "id", "in_force", "prohibits", "permits", "lifts_when", "operative_definition",
})
_TOP_KEYS = frozenset({"version", "roadmap", "source", "externals", "freeze", "items"})

SCHEMA_VERSION = 1


def _reject_unknown(raw: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise RoadmapError(
            f"{where}: unknown key(s) {', '.join(repr(k) for k in unknown)}. "
            "A key this loader ignores is a constraint that silently is not there - "
            "one transposed letter in `gates` put a blocked item at the top of the queue"
        )


def _gate(raw: Any, where: str) -> Gate:
    if not isinstance(raw, Mapping):
        raise RoadmapError(f"{where}: a gate must be a mapping, got {type(raw).__name__}")
    _reject_unknown(raw, _GATE_KEYS, f"{where} gate")
    kind = str(raw.get("kind", "")).strip()
    if not kind:
        raise RoadmapError(f"{where}: a gate with no kind blocks nothing and names nothing")
    run = raw.get("run") or ()
    if isinstance(run, (str, bytes)):
        raise RoadmapError(
            f"{where}: `run` is argv, not a command line. Splitting one is "
            "platform-specific and a Windows path would lose its backslashes"
        )
    gate = Gate(kind=kind, id=str(raw.get("id", "")).strip(), run=tuple(str(p) for p in run))
    if kind == "command" and not gate.run:
        raise RoadmapError(f"{where}: a command gate with no command is satisfied by nothing")
    if kind != "command" and not gate.id:
        raise RoadmapError(f"{where}: a {kind} gate must name what it waits on")
    return gate


def _external(key: str, raw: Any) -> External:
    if not isinstance(raw, Mapping):
        raise RoadmapError(f"external {key}: must be a mapping")
    _reject_unknown(raw, _EXTERNAL_KEYS, f"external {key}")
    owner = str(raw.get("owner", "")).strip()
    if not owner:
        # An external with no owner is a wish. Naming one is the cheapest
        # thing in this file and the only thing that turns a blocker into a
        # conversation somebody can have.
        raise RoadmapError(f"external {key}: no owner. An external nobody owns is a wish")
    attained = raw.get("attained")
    if not isinstance(attained, bool):
        raise RoadmapError(
            f"external {key}: `attained` must be a YAML boolean, got "
            f"{type(attained).__name__}; a truthy string is not an attainment"
        )
    verify = raw.get("verify") or ()
    if isinstance(verify, (str, bytes)):
        raise RoadmapError(f"external {key}: `verify` is argv, not a command line")
    return External(
        id=key,
        title=str(raw.get("title", "")).strip() or key,
        owner=owner,
        attained=attained,
        blocks_because=str(raw.get("blocks_because", "")).strip(),
        note=str(raw.get("note", "")).strip(),
        verify=tuple(str(p) for p in verify),
    )


@dataclass(frozen=True)
class Roadmap:
    """A loaded, fully validated roadmap."""

    name: str
    source: str
    path: Path | None
    items: Mapping[str, RoadmapItem]
    externals: Mapping[str, External]
    freeze: Mapping[str, Any] = field(default_factory=dict)

    def resolve(
        self,
        registry: Registry | None = None,
        attestations: AttestationStore | None = None,
        *,
        at: datetime | None = None,
        run_commands: bool = False,
        timeout: float = DEFAULT_COMMAND_TIMEOUT,
    ) -> RoadmapReport:
        """Evaluate every gate and report what is actionable now.

        `registry` and `attestations` are optional so the roadmap can be read
        where they are not available -- but their absence never produces a
        READY. A band gate with no registry is UNKNOWN, and UNKNOWN blocks.
        """
        at = at or now_utc()
        resolver = (
            BandResolver(registry, attestations)
            if registry is not None and attestations is not None
            else None
        )

        results: dict[str, ItemReadiness] = {}
        for item_id in self.items:
            self._readiness(item_id, resolver, attestations, at, run_commands, timeout, results)

        ordered = tuple(results[i] for i in self.items)
        contradictions = tuple(r for r in ordered if r.contradiction)
        freeze_in_force, freeze_reasons = self._freeze_state(results)
        return RoadmapReport(
            roadmap=self.name,
            evaluated_at=at,
            items=ordered,
            freeze_in_force=freeze_in_force,
            freeze_reasons=freeze_reasons,
            contradictions=contradictions,
        )

    # ---- internals -----------------------------------------------------

    def _readiness(
        self,
        item_id: str,
        resolver: BandResolver | None,
        attestations: AttestationStore | None,
        at: datetime,
        run_commands: bool,
        timeout: float,
        cache: dict[str, ItemReadiness],
        stack: tuple[str, ...] = (),
    ) -> ItemReadiness:
        if item_id in cache:
            return cache[item_id]
        item = self.items[item_id]
        if item_id in stack:
            # Unreachable once the acyclicity invariant has run at load, and
            # kept because a cycle here would otherwise recurse forever.
            raise RoadmapError(f"cycle through {item_id}: {' -> '.join((*stack, item_id))}")

        gates = tuple(
            self._evaluate(
                g, resolver, attestations, at, run_commands, timeout, cache, (*stack, item_id)
            )
            for g in item.gates
        )
        if not gates and not item.ungated_because:
            # `all()` over an empty tuple is True, so an item with no gates used
            # to report READY and sort to the top of the work queue -- and so
            # did an item whose `gates:` key was misspelled, because unknown
            # keys were ignored. A permission-shaped object with no content is
            # permission (threat model class C2). Emptiness now has to be
            # deliberate and stated.
            verdict = UNKNOWN
            gates = (
                GateResult(
                    Gate(kind="item", id=item.id),
                    UNKNOWN,
                    "no gates and no `ungated_because`. An item that waits on nothing "
                    "either says why, or is a typo",
                ),
            )
        elif any(g.verdict == UNKNOWN for g in gates):
            verdict = UNKNOWN
        elif all(g.satisfied for g in gates):
            verdict = READY
        else:
            verdict = BLOCKED

        contradiction = ""
        # A review reported that `partial` items never contradict and proposed
        # widening this to `has_shipped`. Widening it verbatim makes every
        # honestly-partial item a contradiction, which is wrong: for a `partial`
        # item the gates describe what blocks the REMAINDER, not what licensed
        # the part already in the product. W9 is the case -- three releases
        # shipped, the rest waiting on T1, and nothing anomalous about it.
        #
        # So the two halves are checked separately, and the acceptance check
        # below is what covers the shipped half of a partial item:
        #   `shipped` + an unsatisfied gate  -> the item claims completion it
        #                                       does not have
        #   anything shipped + failing acceptance -> the part that is in the
        #                                       product no longer holds
        if item.claims_done and verdict != READY:
            names = ", ".join(g.gate.describe() for g in gates if not g.satisfied)
            contradiction = (
                f"declared {item.state} while {names} is unsatisfied. Either the item is "
                "not done or the gate never applied; both are worth knowing"
            )

        # Acceptance runs for anything that claims work is already in: a
        # command attached to an item nobody has built proves nothing, but one
        # attached to shipped work is the only thing standing between "we
        # shipped W2" and the fact of it.
        accepted: tuple[GateResult, ...] = ()
        if run_commands and item.has_shipped:
            accepted = tuple(
                _run_command(Gate(kind="command", run=cmd), timeout)
                for cmd in item.acceptance_commands
            )
            failed = [a for a in accepted if not a.satisfied]
            if failed:
                # It used to set `contradiction` and leave `verdict` READY, so an
                # item whose own acceptance command failed still sat in the
                # actionable queue with `blockers: []`.
                verdict = BLOCKED
                gates = gates + tuple(
                    GateResult(a.gate, BLOCKED, f"acceptance: {a.detail}") for a in failed
                )
                detail = "; ".join(f"`{' '.join(a.gate.run)}` {a.detail}" for a in failed)
                contradiction = (
                    (contradiction + ". Also: " if contradiction else "")
                    + f"declared {item.state} and its own acceptance fails: {detail}"
                )

        readiness = ItemReadiness(
            item=item, verdict=verdict, gates=gates, contradiction=contradiction,
            acceptance=accepted,
        )
        cache[item_id] = readiness
        return readiness

    def _evaluate(
        self,
        gate: Gate,
        resolver: BandResolver | None,
        attestations: AttestationStore | None,
        at: datetime,
        run_commands: bool,
        timeout: float,
        cache: dict[str, ItemReadiness],
        stack: tuple[str, ...],
    ) -> GateResult:
        if gate.kind == "external":
            ext = self.externals[gate.id]
            if not ext.attained:
                return GateResult(gate, BLOCKED, f"{ext.id} not attained; owned by {ext.owner}")
            if ext.verify:
                # `verify` was parsed, stored, and never executed. It sat in the
                # file directly under `attained: false` reading, in a diff, like
                # proof. An external carrying a verifier is UNKNOWN until the
                # verifier has run: one edited token must not open three items.
                if not run_commands:
                    return GateResult(
                        gate, UNKNOWN,
                        f"{ext.id} declares itself attained and carries a verifier that "
                        "was not run; pass --check",
                    )
                checked = _run_command(Gate(kind="command", run=ext.verify), timeout)
                if not checked.satisfied:
                    return GateResult(
                        gate, BLOCKED,
                        f"{ext.id} is declared attained and its own verifier disagrees: "
                        f"{checked.detail}",
                    )
                return GateResult(gate, READY, f"{ext.id} attained and verified ({ext.owner})")
            return GateResult(gate, READY, f"{ext.id} attained ({ext.owner}), unverified")

        if gate.kind == "item":
            dep = self._readiness(
                gate.id, resolver, attestations, at, run_commands, timeout, cache, stack
            )
            # This used to read `dep.item.claims_done` alone -- the string a
            # human typed. So an upstream item declared `shipped` while its own
            # gates were unsatisfied satisfied this gate, and an upstream whose
            # verdict was UNKNOWN did too: UNKNOWN could not propagate through
            # an item gate at all. Both contradict the module's own headline
            # promise that readiness is computed rather than declared.
            if not dep.item.claims_done:
                return GateResult(gate, BLOCKED, f"{gate.id} is {dep.item.state}, not shipped")
            if dep.verdict == UNKNOWN:
                return GateResult(
                    gate, UNKNOWN,
                    f"{gate.id} says shipped but its own gates cannot be evaluated",
                )
            if dep.verdict != READY:
                return GateResult(
                    gate, BLOCKED,
                    f"{gate.id} says shipped and its own gates are not satisfied - "
                    "see its contradiction",
                )
            return GateResult(gate, READY, f"{gate.id} is {dep.item.state}")

        if gate.kind == "band_attained":
            if resolver is None:
                return GateResult(gate, UNKNOWN, "no registry or attestations to resolve against")
            if gate.id not in resolver.registry.bands:
                return GateResult(gate, UNKNOWN, f"{gate.id} is not a band in this registry")
            status = resolver.status(gate.id, at=at)
            if status.attained and not status.conditional:
                return GateResult(gate, READY, f"{gate.id} attained")
            if status.attained:
                # Attained on a waiver. A waiver expires, so a plan built on
                # one is a plan with a clock on it.
                return GateResult(
                    gate, BLOCKED,
                    f"{gate.id} attained only on waiver(s) "
                    f"{', '.join(status.waiver_ids) or '(unnamed)'}",
                )
            return GateResult(gate, BLOCKED, status.reasons[0] if status.reasons else "not attained")

        if gate.kind == "control_attested":
            if resolver is None or attestations is None:
                return GateResult(gate, UNKNOWN, "no attestation store to resolve against")
            control = resolver.registry.controls.get(gate.id)
            if control is None:
                return GateResult(gate, UNKNOWN, f"{gate.id} is not a control in this registry")
            window = resolver.registry.max_age_for(gate.id)
            if attestations.holds(gate.id, window, at=at):
                return GateResult(gate, READY, f"{gate.id} attested and fresh")
            return GateResult(gate, BLOCKED, attestations.explain(gate.id, window, at=at))

        if gate.kind == "command":
            if not run_commands:
                return GateResult(gate, UNKNOWN, "not run; pass --check to run command gates")
            return _run_command(gate, timeout)

        return GateResult(
            gate, UNKNOWN,
            f"gate kind {gate.kind!r} is not one this version evaluates "
            f"({', '.join(GATE_KINDS)}); an unrecognised gate blocks",
        )

    def _freeze_state(
        self, results: Mapping[str, ItemReadiness]
    ) -> tuple[bool | None, tuple[str, ...]]:
        if not self.freeze:
            return None, ()
        if not self.freeze.get("in_force", False):
            return False, ("the roadmap declares the freeze lifted",)
        reasons: list[str] = []
        for raw in self.freeze.get("lifts_when") or ():
            gate = _gate(raw, "freeze.lifts_when")
            if gate.kind != "item":
                reasons.append(f"{gate.describe()} is not an item gate and cannot be read here")
                continue
            dep = results.get(gate.id)
            if dep is None:
                reasons.append(f"{gate.id} is not an item in this roadmap")
            elif not (dep.item.claims_done and dep.verdict == READY):
                blockers = ", ".join(g.gate.describe() for g in dep.blockers)
                reasons.append(
                    f"{gate.id} is {dep.item.state}"
                    + (f" ({dep.verdict})" if dep.item.claims_done else "")
                    + (f", waiting on {blockers}" if blockers else "")
                )
        return bool(reasons), tuple(reasons)


def _run_command(gate: Gate, timeout: float) -> GateResult:
    try:
        completed = subprocess.run(
            list(gate.run), capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return GateResult(gate, BLOCKED, f"{gate.run[0]!r} not found")
    except OSError as exc:
        return GateResult(gate, BLOCKED, f"could not run it: {exc}")
    except subprocess.TimeoutExpired:
        # A check that hangs has not passed.
        return GateResult(gate, BLOCKED, f"timed out after {timeout:g}s")
    if completed.returncode == 0:
        return GateResult(gate, READY, "exit 0")
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    return GateResult(
        gate, BLOCKED, f"exit {completed.returncode}" + (f": {detail[0][:160]}" if detail else "")
    )


def load_roadmap(path: str | Path | None = None) -> Roadmap:
    """Load and fully validate a roadmap. No partial roadmap, ever."""
    resolved = Path(path) if path else DEFAULT_ROADMAP
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RoadmapError(f"could not read {resolved}: {exc}") from None
    try:
        data = yaml.load(text, Loader=_StrictLoader)
    except RoadmapError:
        raise
    except yaml.YAMLError as exc:
        raise RoadmapError(f"{resolved}: not valid YAML: {exc}") from None
    if not isinstance(data, Mapping):
        raise RoadmapError(f"{resolved}: the roadmap must be a mapping")
    _reject_unknown(data, _TOP_KEYS, str(resolved))
    version = data.get("version")
    if version != SCHEMA_VERSION:
        # A newer file must block an older tool rather than be read under the
        # wrong semantics - the same rule this module already applies to an
        # unrecognised gate kind, not previously applied to its own version.
        raise RoadmapError(
            f"{resolved}: schema version {version!r}, but this build reads "
            f"version {SCHEMA_VERSION}"
        )

    externals = {
        str(k): _external(str(k), v) for k, v in (data.get("externals") or {}).items()
    }

    raw_items = data.get("items") or []
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        raise RoadmapError(f"{resolved}: `items` must be a list")

    items: dict[str, RoadmapItem] = {}
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise RoadmapError(f"{resolved}: an item must be a mapping")
        item_id = str(raw.get("id", "")).strip()
        _reject_unknown(raw, _ITEM_KEYS, f"item {item_id or '<unnamed>'}")
        if not item_id:
            raise RoadmapError(f"{resolved}: an item with no id cannot be depended on")
        if item_id in items:
            raise RoadmapError(f"{resolved}: duplicate item id {item_id}")
        state = str(raw.get("state", "")).strip().lower()
        if state not in ITEM_STATES:
            raise RoadmapError(
                f"{item_id}: state {state!r} is not one of {', '.join(ITEM_STATES)}"
            )
        owner = str(raw.get("owner", "")).strip()
        if not owner:
            raise RoadmapError(f"{item_id}: no owner. An item nobody owns is not scheduled")
        score = raw.get("score")
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
            # `score: true` used to become 1.0. `register.py` had this guard and
            # this loader did not, written by the same hand in the same week.
            raise RoadmapError(f"{item_id}: score must be a number or null, got {score!r}")
        raw_gates = raw.get("gates")
        if raw_gates is not None and (
            not isinstance(raw_gates, Sequence) or isinstance(raw_gates, (str, bytes))
        ):
            raise RoadmapError(f"{item_id}: `gates` must be a list, got {type(raw_gates).__name__}")
        items[item_id] = RoadmapItem(
            id=item_id,
            title=str(raw.get("title", "")).strip() or item_id,
            state=state,
            owner=owner,
            gates=tuple(_gate(g, item_id) for g in (raw.get("gates") or ())),
            score=float(score) if score is not None else None,
            register_ref=str(raw.get("register_ref", "")).strip(),
            shipped_in=tuple(str(v) for v in (raw.get("shipped_in") or ())),
            remaining=tuple(str(v) for v in (raw.get("remaining") or ())),
            note=str(raw.get("note", "")).strip(),
            acceptance=tuple(raw.get("acceptance") or ()),
            ungated_because=str(raw.get("ungated_because", "")).strip(),
        )
        for entry in items[item_id].acceptance:
            if not isinstance(entry, Mapping):
                raise RoadmapError(f"{item_id}: an acceptance entry must be a mapping")
            _reject_unknown(entry, _ACCEPTANCE_KEYS, f"{item_id} acceptance")
            run = entry.get("run")
            if isinstance(run, (str, bytes)):
                raise RoadmapError(f"{item_id}: acceptance `run` is argv, not a command line")
            # `runs:` for `run:` used to be discarded in silence, leaving
            # `proves: The thing is proven.` in the file and nothing running.
            if isinstance(run, Mapping) or not isinstance(run, Sequence) or not run:
                raise RoadmapError(
                    f"{item_id}: acceptance needs a non-empty `run` list. An acceptance "
                    "that never executes is the claim this file exists to stop the "
                    "roadmap being made of"
                )
            if not all(isinstance(part, str) for part in run):
                raise RoadmapError(
                    f"{item_id}: acceptance `run` must be a list of strings; a mapping "
                    "iterates its keys and becomes a different, passing command"
                )

    roadmap = Roadmap(
        name=str(data.get("roadmap", "")).strip() or resolved.stem,
        source=str(data.get("source", "")).strip(),
        path=resolved,
        items=items,
        externals=externals,
        freeze=dict(data.get("freeze") or {}),
    )
    _assert_references_resolve(roadmap)
    _assert_acyclic(roadmap)
    _assert_freeze_is_readable(roadmap)
    return roadmap


# ---- invariants --------------------------------------------------------


def _assert_references_resolve(roadmap: Roadmap) -> None:
    """Every named dependency exists.

    A gate on an item id nobody defined, or an external nobody declared, would
    otherwise evaluate to UNKNOWN and be indistinguishable from a real unknown.
    A typo must be a load failure, not a permanent mystery blocker.
    """
    for item in roadmap.items.values():
        for gate in item.gates:
            if gate.kind == "item" and gate.id not in roadmap.items:
                raise RoadmapError(f"{item.id}: gate names item {gate.id}, which does not exist")
            if gate.kind == "external" and gate.id not in roadmap.externals:
                raise RoadmapError(
                    f"{item.id}: gate names external {gate.id}, which is not declared. "
                    "Declare it with an owner, or it is a wish rather than a blocker"
                )


def _assert_acyclic(roadmap: Roadmap) -> None:
    state: dict[str, int] = {}

    def visit(node: str, path: tuple[str, ...]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            raise RoadmapError(f"cycle in item dependencies: {' -> '.join((*path, node))}")
        state[node] = 1
        for gate in roadmap.items[node].gates:
            if gate.kind == "item":
                visit(gate.id, (*path, node))
        state[node] = 2

    for node in roadmap.items:
        visit(node, ())


def _assert_freeze_is_readable(roadmap: Roadmap) -> None:
    """A freeze whose lift condition cannot be evaluated never lifts.

    That is safe and useless: it becomes a permanent state nobody can discharge,
    which is how a freeze stops being believed.
    """
    if not roadmap.freeze:
        return
    if not isinstance(roadmap.freeze.get("in_force"), bool):
        raise RoadmapError("freeze.in_force must be a YAML boolean")
    conditions = roadmap.freeze.get("lifts_when") or ()
    if roadmap.freeze.get("in_force") and not conditions:
        raise RoadmapError(
            "the freeze is in force with no lift condition. A freeze that cannot be "
            "discharged is one that gets ignored instead of lifted"
        )
    for raw in conditions:
        gate = _gate(raw, "freeze.lifts_when")
        if gate.kind == "item" and gate.id not in roadmap.items:
            raise RoadmapError(f"freeze.lifts_when names item {gate.id}, which does not exist")
