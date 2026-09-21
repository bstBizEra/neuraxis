"""The BizTrust assist agent — what an unattended agent may do next, decided mechanically.

The BizTrust Docs Hub (`bstBizEra/biztrust_guide`) records its operational state
in two files, `badf/current-state.json` and `badf/next-actions.json`, and its
charter (`AGENTS.md`) in prose. An agent resuming without a human present has to
answer one question before it does anything: **which of the recorded actions is
mine to perform?**

Today that answer is read out of prose. NS-041's stop condition is the sentence
*"An agent posts the waiver"*; NS-040's is *"An agent supplies either answer"*.
Both are correct, both are binding, and both are enforced by an agent reading
them carefully — which is the control this framework exists to replace. An
instruction to be careful is not a control. Under schedule pressure, *"blocked
on a human"* becomes *"the human would have said yes"*, and the record that was
supposed to stop the action is the record that gets reinterpreted.

So this module decides it instead, and the decision is refusal-by-default:

    AGENT_EXECUTABLE   every clause below was satisfied AND the gate allowed it
    HUMAN_ONLY         some clause reserved it to a person
    REFUSED            the record could not be read well enough to say

There is no fourth answer. An action this module cannot classify is HUMAN_ONLY,
an action whose record is malformed is REFUSED, and neither is a permission.

**Two independent locks.** An action is executable only if the *record* grants
it (sections 1-5 below) *and* `GovernanceGate` ALLOWs an authority request for
it. The record's own authority string never substitutes for the gate: a line of
JSON in another repository cannot open a band here. Either lock alone refuses.

**This module has no write path.** It reads two JSON files and runs read-only
git. It cannot post a comment, close a ticket, edit the hub or push a branch,
and the git allowlist (`_GIT_READ_ONLY`) is in code so that adding one would be
a visible change rather than an argument. Automation may propose, never merge:
what it produces is a report a person or a CI job reads.

The classification clauses, each a constant in this module rather than a
setting, for ADR-0006's reason — *a bound that exists to constrain a record
cannot live in that record*:

1. **Authority.** The action's `authority` token stream must contain a grant
   phrase and no veto token. Absent, empty or unrecognised authority is
   HUMAN_ONLY (ADR-0002's shape: absence denies).
2. **Seat.** `owner_role` must map, through `HUB_ROLE_TO_NEURAXIS`, onto a role
   this registry grants. An unmapped role is HUMAN_ONLY, and the mapping may
   not name a human seat — asserted at import.
3. **Stop conditions.** A stop condition naming an agent, automation or a bot
   as the actor of the prohibited act makes the action HUMAN_ONLY. Deliberately
   over-broad: a false positive costs an action not taken; a false negative is
   an agent doing the thing the record forbids.
4. **Evidence.** An action whose required evidence can only be produced by a
   person — *"a comment with no agent marker"*, *"a written answer per tenant"* —
   is HUMAN_ONLY, because an agent that cannot produce the evidence cannot
   complete the action, only appear to.
5. **The record as a whole.** One work package across both files, the primary
   action present and named, priorities 1..n, the latest checkpoint on disk,
   `resume_decision` CONTINUE, and an observable HEAD to bind evidence to
   (AGENTS.md section 9). Any failure poisons the whole run rather than the one
   action: a record that disagrees with itself is not a record some of which
   can be trusted.

**The self-test is not optional.** A classifier that answered HUMAN_ONLY to
everything would pass every deny-assertion ever written against it while being
completely broken, and one that answered AGENT_EXECUTABLE to everything would
be worse. `selftest()` runs both a positive control and a vacuity probe before
any real record is read, and a run whose self-test is not live reports REFUSED
with nothing executable. This is the providers' four conformance rules applied
to the thing that decides what an agent may do.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .attestation import AttestationStore
from .errors import NeuraxisError
from .gate import GovernanceGate
from .model import AuthorityRequest, Decision, Verdict, now_utc

# ---------------------------------------------------------------------------
# Verdict vocabulary
# ---------------------------------------------------------------------------

AGENT_EXECUTABLE = "AGENT_EXECUTABLE"
HUMAN_ONLY = "HUMAN_ONLY"
REFUSED = "REFUSED"

TRIAGE_VERDICTS = (AGENT_EXECUTABLE, HUMAN_ONLY, REFUSED)

#: The hub's own resume vocabulary (AGENTS.md section 3). An unrecognised value
#: is not treated as CONTINUE; it is treated as RECOVERY_REQUIRED, because a
#: state machine that has left its own alphabet is not in a known state.
RESUME_DECISIONS = (
    "CONTINUE",
    "BLOCKED",
    "WAIT_FOR_AUTHORITY",
    "RECOVERY_REQUIRED",
    "COMPLETE",
)

# ---------------------------------------------------------------------------
# Clause 1 — authority
# ---------------------------------------------------------------------------

#: Phrases that, appearing as consecutive whole tokens in an action's
#: `authority`, are a grant an unattended agent may act on. Phrases, not
#: substrings: `PROCEED_ON_YOUR_CALL` must appear in that order, so a token
#: containing "call" somewhere cannot be read as permission to proceed.
AUTHORITY_GRANT_PHRASES: tuple[tuple[str, ...], ...] = (
    ("PROCEED", "ON", "YOUR", "CALL"),
    ("AGENT", "EXECUTABLE"),
    ("GRANTED", "TO", "AGENT"),
)

#: Any one of these as a whole token vetoes, whatever else the string says, and
#: the veto is applied after the grant so it cannot be outvoted. `NOT` is here
#: because `NOT_GRANTED` and `AUTHORITY_NOT_YET_GRANTED` must both stop, and a
#: grammar that parses negation is a grammar that can get negation wrong.
#:
#: These are modal tokens — words about whether the thing is *reserved* — and
#: deliberately not the names of roles. That distinction was found rather than
#: designed. The first cut also vetoed `OPERATOR`, `REVIEWER`, `BROKER` and
#: `PRINCIPAL`, reasoning that a human role named in an authority string means
#: a human owns it; `selftest()`'s positive control failed on its first run,
#: against the hub's own real grant
#: `OPERATOR_INSTRUCTION_2026_09_05_PROCEED_ON_YOUR_CALL_PROPOSED_ONLY`. The
#: operator is normally the *source* of a grant, so vetoing their name refuses
#: every instruction they give — and a classifier that refuses everything proves
#: nothing while looking maximally safe. That is the failure the vacuity rule
#: names, arriving from the cautious side, which is the side nobody inspects.
#:
#: `HUMAN` stays: an authority string naming a human at all is at best
#: ambiguous about who holds the action, and ambiguity resolves to the person.
#: Role nouns are not lost either — clause 2 reads the seat from `owner_role`,
#: which is the field that actually records it, rather than inferring it from
#: words in a grant.
AUTHORITY_VETO_TOKENS = frozenset({
    "NOT", "NO", "NEVER", "NEITHER",
    "HUMAN",
    "UNKNOWN", "UNCLEAR", "TBD", "TBC", "HOLD",
    "SIGNOFF", "SIGNED",
})

#: Vetoes matched on a leading stem rather than in full, because the exact set
#: above is defeated by an inflection: the first cut listed `APPROVAL` and
#: `APPROVE`, and `PROCEED_ON_YOUR_CALL_WHEN_APPROVED` classified as
#: executable — a grant conditional on an approval that has not happened, read
#: as the approval.
#:
#: Stems only for words whose every inflection reserves the action. The
#: negations above stay exact on purpose: `NO` as a stem would veto `NOW`, and
#: a veto list that refuses `PROCEED_NOW` is the over-refusal the vacuity
#: probe exists to catch. Here, refusing too much is the cheap error and
#: refusing too little is the expensive one, but only where the word carries
#: the meaning on its own.
AUTHORITY_VETO_STEMS = (
    "REQUIR",      # REQUIRE, REQUIRED, REQUIRES, REQUIREMENT
    "WAIT",        # WAIT, WAITING, WAITS
    "PEND",        # PENDING, PENDS
    "BLOCK",       # BLOCKED, BLOCKING
    "DEFER",       # DEFERRED, DEFERRAL
    "EXPIR",       # EXPIRED, EXPIRY, EXPIRES
    "LAPS",        # LAPSED, LAPSE
    "REVOK",       # REVOKED, REVOKE
    "WITHDRAW",    # WITHDRAWN, WITHDRAWAL
    "SUSPEND",     # SUSPENDED, SUSPENSION
    "RATIF",       # RATIFY, RATIFIED, RATIFICATION
    "APPROV",      # APPROVE, APPROVED, APPROVAL
    "ESCALAT",     # ESCALATE, ESCALATED, ESCALATION
)


def _veto_tokens(tokens: Sequence[str]) -> list[str]:
    """Every token in the stream that reserves the action, exact or by stem."""
    return sorted(
        {
            token
            for token in tokens
            if token in AUTHORITY_VETO_TOKENS
            or any(token.startswith(stem) for stem in AUTHORITY_VETO_STEMS)
        }
    )

# ---------------------------------------------------------------------------
# Clause 2 — the seat
# ---------------------------------------------------------------------------

#: Hub owner_role -> a role this registry grants. Deliberately small. A hub
#: role absent from this mapping has no neuraxis role, and an action with no
#: role never reaches the gate: it is HUMAN_ONLY on clause 2.
HUB_ROLE_TO_NEURAXIS: Mapping[str, str] = {
    "documentation-engineer": "drafter",
    "continuity-engineer": "drafter",
    "validation-engineer": "drafter",
}

#: A seat a person occupies. The mapping may not contain one — checked at
#: import, below, so that adding `"human-reviewer": "operator"` fails to import
#: rather than quietly handing an agent a reviewer's chair.
HUMAN_SEAT_WORDS = (
    "human", "owner", "reviewer", "operator", "principal", "broker",
    "legal", "compliance", "director", "executive", "counsel", "auditor",
)

# ---------------------------------------------------------------------------
# Clause 3 — stop conditions
# ---------------------------------------------------------------------------

#: A stop condition mentioning one of these is about an agent doing the thing,
#: and the agent reading it is the agent it is about.
AGENT_WORDS = (
    "agent", "agents", "automation", "automated", "bot", "bots",
    "llm", "model", "assistant", "copilot", "claude", "machine",
)

# ---------------------------------------------------------------------------
# Clause 4 — evidence only a person can produce
# ---------------------------------------------------------------------------

HUMAN_EVIDENCE_PHRASES = (
    "no agent marker",
    "a human",
    "human decision",
    "the operator",
    "operator's role",
    "a written answer",
    "signed",
    "sign-off",
    "signoff",
    "seat",
)

# ---------------------------------------------------------------------------
# Clause 5 — the record, and the observation it is reconciled against
# ---------------------------------------------------------------------------

#: The only git subcommands this module will run. An allowlist rather than a
#: denylist, and in code rather than in config, because the property it holds
#: is "this module cannot change the repository it is reading".
_GIT_READ_ONLY = frozenset({"rev-parse", "status", "log", "merge-base", "symbolic-ref"})

_SHA40 = re.compile(r"^[0-9a-f]{40}$")

#: Fields an action must carry to be classified at all. A missing one is not a
#: permissive default; it is REFUSED.
_ACTION_REQUIRED = ("id", "action", "owner_role", "authority")

_CAPABILITY = "IL-06"  # Actionable, BAND-B: "What action should I perform now?"


class AssistError(NeuraxisError):
    """The hub could not be read well enough to decide anything about it."""


def _assert_no_human_seat_in_mapping() -> None:
    for hub_role in HUB_ROLE_TO_NEURAXIS:
        lowered = hub_role.lower()
        for word in HUMAN_SEAT_WORDS:
            if word in lowered:
                raise AssistError(
                    f"HUB_ROLE_TO_NEURAXIS maps {hub_role!r}, which names a human seat "
                    f"({word!r}). A seat a person occupies is not an agent's to fill, and "
                    f"this mapping is the only place that could hand one over."
                )


_assert_no_human_seat_in_mapping()


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NextAction:
    """One entry of `badf/next-actions.json`, as read rather than as intended."""

    id: str
    action: str
    owner_role: str
    authority: str
    primary: bool = False
    priority: int | None = None
    prerequisites: tuple[str, ...] = ()
    evidence_required: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    fallback: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, index: int) -> "NextAction":
        if not isinstance(raw, Mapping):
            raise AssistError(f"action at index {index}: expected an object")
        missing = [k for k in _ACTION_REQUIRED if not str(raw.get(k, "")).strip()]
        if missing:
            raise AssistError(
                f"action at index {index} ({raw.get('id', '<unnamed>')!r}): "
                f"missing or empty {', '.join(missing)}"
            )
        priority = raw.get("priority")
        if priority is not None and (isinstance(priority, bool) or not isinstance(priority, int)):
            raise AssistError(
                f"action {raw['id']!r}: priority must be an integer, "
                f"got {type(priority).__name__}"
            )
        primary = raw.get("primary", False)
        if not isinstance(primary, bool):
            # `"primary": "false"` is a truthy string. The primary action is the
            # one the whole record points at; it is not decided by a coercion.
            raise AssistError(
                f"action {raw['id']!r}: primary must be a JSON boolean, "
                f"got {type(primary).__name__} ({primary!r})"
            )
        return cls(
            id=str(raw["id"]).strip(),
            action=str(raw["action"]).strip(),
            owner_role=str(raw["owner_role"]).strip(),
            authority=str(raw["authority"]).strip(),
            primary=primary,
            priority=priority,
            prerequisites=_strings(raw.get("prerequisites"), f"{raw['id']}.prerequisites"),
            evidence_required=_strings(raw.get("evidence_required"), f"{raw['id']}.evidence_required"),
            stop_conditions=_strings(raw.get("stop_conditions"), f"{raw['id']}.stop_conditions"),
            fallback=str(raw.get("fallback", "")).strip(),
        )


@dataclass(frozen=True)
class HubState:
    """`badf/current-state.json`, reduced to what a resume decision needs."""

    project_id: str
    repository: str
    work_package_id: str
    work_package_state: str
    resume_decision: str
    primary_next_action_id: str
    latest_checkpoint: str
    branch: str
    baseline_commit: str
    updated_at: str
    scope: tuple[str, ...] = ()
    stop_reason: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HubState":
        if not isinstance(raw, Mapping):
            raise AssistError("current-state: expected a JSON object at the top level")
        wp = raw.get("active_work_package")
        if not isinstance(wp, Mapping):
            raise AssistError("current-state: active_work_package is absent or not an object")
        source = raw.get("source")
        source = source if isinstance(source, Mapping) else {}
        resume = str(raw.get("resume_decision", "")).strip().upper()
        return cls(
            project_id=str(raw.get("project_id", "")).strip(),
            repository=str(raw.get("repository", "")).strip(),
            work_package_id=str(wp.get("id", "")).strip(),
            work_package_state=str(wp.get("state", "")).strip(),
            resume_decision=resume,
            primary_next_action_id=str(raw.get("primary_next_action_id", "")).strip(),
            latest_checkpoint=str(raw.get("latest_checkpoint") or "").strip(),
            branch=str(source.get("branch", "")).strip(),
            baseline_commit=str(source.get("baseline_commit", "")).strip(),
            updated_at=str(raw.get("updated_at", "")).strip(),
            scope=_strings(wp.get("scope"), "active_work_package.scope"),
            stop_reason=str(raw.get("stop_reason") or "").strip(),
        )


@dataclass(frozen=True)
class Observed:
    """What git says, as opposed to what the record says.

    `reachable` False is not a fault by itself — a hub read from a tarball has
    no git — but it removes the revision binding, and with it the permission to
    execute anything, because evidence that names no revision satisfies no
    clause of AGENTS.md section 9.
    """

    reachable: bool
    head: str = ""
    branch: str = ""
    dirty: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "head": self.head,
            "branch": self.branch,
            "dirty": self.dirty,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Triage:
    """One action's classification, and the clause that produced it."""

    action_id: str
    verdict: str
    clause: str
    reasons: tuple[str, ...]
    owner_role: str = ""
    neuraxis_role: str = ""
    gate: dict[str, Any] | None = None

    @property
    def executable(self) -> bool:
        """Both locks, or nothing.

        `classify()` answers AGENT_EXECUTABLE for the record's half alone,
        which is what that function is for. A *report* that counted it would be
        announcing a permission the gate never granted — and the first live run
        of this module against the hub did exactly that, listing NS-043 as
        performable under a run that had refused to reach the gate at all. So
        the property asks for the gate's ALLOW as well, rather than trusting
        every path through `assist()` to relabel correctly. The relabelling is
        still done; this is the second lock on the second lock.
        """
        return (
            self.verdict == AGENT_EXECUTABLE
            and isinstance(self.gate, dict)
            and self.gate.get("decision") == Decision.ALLOW.value
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "verdict": self.verdict,
            "clause": self.clause,
            "reasons": list(self.reasons),
            "owner_role": self.owner_role,
            "neuraxis_role": self.neuraxis_role,
            "gate": self.gate,
        }


@dataclass(frozen=True)
class SelfTest:
    """Positive control and vacuity probe for the classifier itself."""

    positive_control: bool
    vacuity_probe: bool
    detail: tuple[str, ...] = ()

    @property
    def live(self) -> bool:
        return self.positive_control and self.vacuity_probe

    def to_dict(self) -> dict[str, Any]:
        return {
            "live": self.live,
            "positive_control": self.positive_control,
            "vacuity_probe": self.vacuity_probe,
            "detail": list(self.detail),
        }


@dataclass(frozen=True)
class AssistReport:
    """One unattended run: what was read, what it means, what may be done."""

    decision: Decision
    reasons: tuple[str, ...]
    triage: tuple[Triage, ...] = ()
    faults: tuple[str, ...] = ()
    selftest: SelfTest | None = None
    state: HubState | None = None
    observed: Observed = field(default_factory=lambda: Observed(reachable=False))
    evaluated_at: datetime = field(default_factory=now_utc)

    @property
    def executable(self) -> tuple[Triage, ...]:
        return tuple(t for t in self.triage if t.executable)

    @property
    def permits_action(self) -> bool:
        return self.decision.permits_action and bool(self.executable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "faults": list(self.faults),
            "executable": [t.action_id for t in self.executable],
            "triage": [t.to_dict() for t in self.triage],
            "selftest": self.selftest.to_dict() if self.selftest else None,
            "state": _state_dict(self.state),
            "observed": self.observed.to_dict(),
            "evaluated_at": self.evaluated_at.isoformat(),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _state_dict(state: HubState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "project_id": state.project_id,
        "repository": state.repository,
        "work_package_id": state.work_package_id,
        "work_package_state": state.work_package_state,
        "resume_decision": state.resume_decision,
        "primary_next_action_id": state.primary_next_action_id,
        "latest_checkpoint": state.latest_checkpoint,
        "branch": state.branch,
        "baseline_commit": state.baseline_commit,
        "updated_at": state.updated_at,
        "scope": list(state.scope),
    }


# ---------------------------------------------------------------------------
# Parsing helpers — every one of them fails closed
# ---------------------------------------------------------------------------


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AssistError(f"{label}: expected an array of strings, got {type(value).__name__}")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise AssistError(f"{label}[{i}]: expected a string, got {type(item).__name__}")
        out.append(item.strip())
    return tuple(out)


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        # utf-8-sig, as every other reader in this package does. PowerShell
        # writes a BOM by default, and the hub is maintained from Windows as
        # well as CI. Read as plain utf-8, a BOM makes `json.loads` raise and
        # the run ESCALATEs with "not valid JSON" — a refusal that looks like
        # the tool working and names the wrong cause. Fail-closed for an
        # encoding reason is still a correct answer for the wrong reason.
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise AssistError(f"{label}: cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        # ValueError covers JSONDecodeError and UnicodeDecodeError alike. A
        # single bad byte must produce a refusal, not a traceback a caller
        # might read as "no findings".
        raise AssistError(f"{label}: {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AssistError(
            f"{label}: expected a JSON object at the top level of {path}, "
            f"found {type(data).__name__}"
        )
    return data


def _tokens(text: str) -> tuple[str, ...]:
    """Uppercase word tokens, with every separator treated alike.

    `OPERATOR_INSTRUCTION_2026_09_05_PROCEED_ON_YOUR_CALL_PROPOSED_ONLY` and
    `operator instruction ... proceed on your call` produce the same stream, so
    the clauses below cannot be evaded by changing the punctuation.
    """
    return tuple(t for t in re.split(r"[^A-Za-z0-9]+", text.upper()) if t)


def _has_phrase(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    n = len(phrase)
    if n == 0 or len(tokens) < n:
        return False
    return any(tuple(tokens[i : i + n]) == tuple(phrase) for i in range(len(tokens) - n + 1))


def _mentions(text: str, words: Iterable[str]) -> str | None:
    """The first of `words` appearing in `text` as a whole word, or None."""
    lowered = text.lower()
    for word in words:
        if re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", lowered):
            return word
    return None


def _contains_phrase(text: str, phrases: Iterable[str]) -> str | None:
    """The first phrase appearing in `text`, bounded at both ends.

    Bounded rather than a plain substring, so `"signed"` does not fire inside
    `"designed"`. Over-refusing is the cheap direction here, but an over-refusal
    nobody can explain from the text is indistinguishable from a bug, and the
    report has to be able to name the phrase it matched.
    """
    lowered = text.lower()
    for phrase in phrases:
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", lowered):
            return phrase
    return None


# ---------------------------------------------------------------------------
# Clause evaluation
# ---------------------------------------------------------------------------


def classify(action: NextAction, *, roles: Mapping[str, str] | None = None) -> Triage:
    """Clauses 1-4 for one action. The gate is applied separately, and after.

    Order matters only for which reason is reported first; every clause is a
    veto, so no order changes the answer. Clause 1 runs first because an
    action's authority is the thing a reader looks at.
    """
    mapping = _roles(roles)

    # --- Clause 1: authority.
    tokens = _tokens(action.authority)
    if not tokens:
        return Triage(
            action_id=action.id,
            verdict=HUMAN_ONLY,
            clause="authority",
            reasons=("the action records no authority, and absent authority is not a grant",),
            owner_role=action.owner_role,
        )
    veto = _veto_tokens(tokens)
    granted = [p for p in AUTHORITY_GRANT_PHRASES if _has_phrase(tokens, p)]
    if veto:
        return Triage(
            action_id=action.id,
            verdict=HUMAN_ONLY,
            clause="authority",
            reasons=(
                f"authority {action.authority!r} carries the reserving token(s) "
                f"{', '.join(veto)}",
                "a grant phrase does not outvote a veto token; the veto is applied last",
            )
            if granted
            else (
                f"authority {action.authority!r} carries the reserving token(s) "
                f"{', '.join(veto)}",
            ),
            owner_role=action.owner_role,
        )
    if not granted:
        return Triage(
            action_id=action.id,
            verdict=HUMAN_ONLY,
            clause="authority",
            reasons=(
                f"authority {action.authority!r} matches no grant phrase "
                f"({'; '.join(' '.join(p) for p in AUTHORITY_GRANT_PHRASES)})",
                "an unrecognised authority string is not read generously",
            ),
            owner_role=action.owner_role,
        )

    # --- Clause 2: the seat.
    neuraxis_role = mapping.get(action.owner_role, "")
    if not neuraxis_role:
        return Triage(
            action_id=action.id,
            verdict=HUMAN_ONLY,
            clause="seat",
            reasons=(
                f"owner_role {action.owner_role!r} maps to no role this registry grants",
                f"mapped roles: {', '.join(sorted(mapping)) or '<none>'}",
            ),
            owner_role=action.owner_role,
        )

    # --- Clause 3: stop conditions.
    for condition in action.stop_conditions:
        word = _mentions(condition, AGENT_WORDS)
        if word:
            return Triage(
                action_id=action.id,
                verdict=HUMAN_ONLY,
                clause="stop-condition",
                reasons=(
                    f"stop condition names {word!r}: {condition!r}",
                    "the agent reading a stop condition about an agent is the agent it is about",
                ),
                owner_role=action.owner_role,
                neuraxis_role=neuraxis_role,
            )

    # --- Clause 4: evidence a person must produce.
    for requirement in action.evidence_required:
        phrase = _contains_phrase(requirement, HUMAN_EVIDENCE_PHRASES)
        if phrase:
            return Triage(
                action_id=action.id,
                verdict=HUMAN_ONLY,
                clause="evidence",
                reasons=(
                    f"required evidence is a person's to produce ({phrase!r}): {requirement!r}",
                    "an agent that cannot produce the evidence cannot complete the action, "
                    "only appear to",
                ),
                owner_role=action.owner_role,
                neuraxis_role=neuraxis_role,
            )
    if not action.evidence_required:
        return Triage(
            action_id=action.id,
            verdict=HUMAN_ONLY,
            clause="evidence",
            reasons=(
                "the action states no evidence requirement",
                "work whose completion nothing would evidence is not unattended work",
            ),
            owner_role=action.owner_role,
            neuraxis_role=neuraxis_role,
        )

    return Triage(
        action_id=action.id,
        verdict=AGENT_EXECUTABLE,
        clause="record",
        reasons=(
            f"authority {action.authority!r} grants it, no veto token, no stop condition "
            f"naming an agent, and evidence an agent can produce",
            "record-level only; the gate decides separately",
        ),
        owner_role=action.owner_role,
        neuraxis_role=neuraxis_role,
    )


def _roles(roles: Mapping[str, str] | None) -> Mapping[str, str]:
    """A caller may narrow the mapping and may not widen it.

    Same rule as `WaiverPolicy`'s ceilings: a bound that exists to constrain a
    caller cannot be set by that caller. An entry not already in
    `HUB_ROLE_TO_NEURAXIS`, or one that renames the neuraxis role it maps to,
    is dropped rather than honoured.
    """
    if roles is None:
        return HUB_ROLE_TO_NEURAXIS
    return {
        hub: nx
        for hub, nx in roles.items()
        if HUB_ROLE_TO_NEURAXIS.get(hub) == nx
    }


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str, timeout: float = 15.0) -> tuple[int, str] | None:
    """Run one read-only git command, or return None if it could not run."""
    if not args or args[0] not in _GIT_READ_ONLY:
        raise AssistError(
            f"git {args[0] if args else '<empty>'!r} is not on the read-only allowlist "
            f"({', '.join(sorted(_GIT_READ_ONLY))}). This module does not write to the hub."
        )
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout.strip()


def observe(root: Path) -> Observed:
    """What the checkout actually is. Never raises; an unreadable checkout is a fact."""
    head = _git(root, "rev-parse", "HEAD")
    if head is None or head[0] != 0 or not _SHA40.match(head[1]):
        return Observed(
            reachable=False,
            detail="git could not report a HEAD commit for this directory",
        )
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(root, "status", "--porcelain")
    return Observed(
        reachable=True,
        head=head[1],
        branch=branch[1] if branch and branch[0] == 0 else "",
        dirty=bool(status and status[0] == 0 and status[1]),
        detail="observed from the working tree",
    )


# ---------------------------------------------------------------------------
# Loading the record
# ---------------------------------------------------------------------------


def load_hub(
    hub: str | Path,
    *,
    state_path: str | Path | None = None,
    actions_path: str | Path | None = None,
) -> tuple[HubState, tuple[NextAction, ...]]:
    """Read both BADF files, or raise. There is no partial success here."""
    root = Path(hub)
    state_file = Path(state_path) if state_path else root / "badf" / "current-state.json"
    actions_file = Path(actions_path) if actions_path else root / "badf" / "next-actions.json"

    state = HubState.from_dict(_load_json(state_file, "current-state"))
    raw_actions = _load_json(actions_file, "next-actions")

    entries = raw_actions.get("actions")
    if not isinstance(entries, list):
        raise AssistError("next-actions: `actions` is absent or is not an array")
    if not entries:
        raise AssistError("next-actions: `actions` is empty; a record with no action is not a plan")
    actions = tuple(NextAction.from_dict(raw, index=i) for i, raw in enumerate(entries))

    declared_wp = str(raw_actions.get("work_package_id", "")).strip()
    if declared_wp != state.work_package_id:
        raise AssistError(
            f"the two records name different work packages: current-state says "
            f"{state.work_package_id!r}, next-actions says {declared_wp!r}. "
            f"AGENTS.md section 4: the agent records the conflict and stops."
        )
    return state, actions


def record_faults(state: HubState, actions: Sequence[NextAction], *, root: Path) -> tuple[str, ...]:
    """Clause 5. Everything that makes the record untrustworthy as a whole."""
    faults: list[str] = []

    ids = [a.id for a in actions]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        faults.append(f"duplicate action id(s): {', '.join(duplicates)}")

    primaries = [a.id for a in actions if a.primary]
    if len(primaries) != 1:
        faults.append(
            f"exactly one action must be primary; found {len(primaries)}"
            + (f" ({', '.join(primaries)})" if primaries else "")
        )
    elif state.primary_next_action_id != primaries[0]:
        faults.append(
            f"current-state names {state.primary_next_action_id!r} as the primary action "
            f"and next-actions marks {primaries[0]!r}"
        )
    if state.primary_next_action_id and state.primary_next_action_id not in ids:
        faults.append(
            f"current-state's primary_next_action_id {state.primary_next_action_id!r} "
            f"names no action in next-actions"
        )

    priorities = [a.priority for a in actions]
    if any(p is None for p in priorities):
        faults.append("every action must carry a priority; at least one does not")
    elif sorted(p for p in priorities if p is not None) != list(range(1, len(actions) + 1)):
        faults.append(
            f"priorities must be 1..{len(actions)} with no gap or repeat; found "
            f"{sorted(p for p in priorities if p is not None)}"
        )

    if not state.latest_checkpoint:
        faults.append("current-state names no latest_checkpoint")
    elif not (root / state.latest_checkpoint).is_file():
        faults.append(
            f"the recorded checkpoint {state.latest_checkpoint!r} is not a file in this checkout"
        )

    if state.resume_decision not in RESUME_DECISIONS:
        faults.append(
            f"resume_decision {state.resume_decision!r} is not one of "
            f"{', '.join(RESUME_DECISIONS)}; a state machine outside its own alphabet "
            f"is not in a known state"
        )

    if state.baseline_commit and not _SHA40.match(state.baseline_commit):
        faults.append(
            f"source.baseline_commit {state.baseline_commit!r} is not a 40-character sha"
        )

    return tuple(faults)


# ---------------------------------------------------------------------------
# The self-test: positive control and vacuity probe
# ---------------------------------------------------------------------------

_PROBE_HUMAN = NextAction(
    id="PROBE-HUMAN",
    action="Record a decision only a person may take.",
    owner_role="human-reviewer",
    authority="HUMAN_DECISION_REQUIRED",
    evidence_required=("A comment on the issue with no agent marker",),
    stop_conditions=("An agent supplies the answer",),
)

_PROBE_AGENT = NextAction(
    id="PROBE-AGENT",
    action="Regenerate the control page from its fixture and report the diff.",
    owner_role="documentation-engineer",
    authority="OPERATOR_INSTRUCTION_2026_09_05_PROCEED_ON_YOUR_CALL_PROPOSED_ONLY",
    evidence_required=("The runner's output attached to the pull request",),
    stop_conditions=("The fixture cannot be rebuilt from the recorded baseline",),
)


def selftest() -> SelfTest:
    """Prove the classifier is live and discriminating before it is trusted.

    A classifier that refuses everything satisfies every deny-assertion in the
    suite and licenses nothing; one that permits everything satisfies none of
    them and licenses everything. Both are broken, and only one of them looks
    broken. So both directions are probed, every run.
    """
    detail: list[str] = []

    positive = classify(_PROBE_AGENT)
    if positive.verdict != AGENT_EXECUTABLE:
        detail.append(
            f"positive control failed: an action drafted to be agent-executable came back "
            f"{positive.verdict} on clause {positive.clause!r} "
            f"({'; '.join(positive.reasons)}). The classifier refuses everything and "
            f"proves nothing."
        )

    vacuity = classify(_PROBE_HUMAN)
    if vacuity.verdict != HUMAN_ONLY:
        detail.append(
            f"vacuity probe failed: an action reserved to a person in every clause came back "
            f"{vacuity.verdict}. A check that cannot fail discriminates nothing."
        )

    return SelfTest(
        positive_control=positive.verdict == AGENT_EXECUTABLE,
        vacuity_probe=vacuity.verdict == HUMAN_ONLY,
        detail=tuple(detail),
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def assist(
    hub: str | Path,
    *,
    registry: Any,
    store: AttestationStore,
    identity: str = "neuraxis-assist",
    verifier: str | None = None,
    rollback_tested: bool = False,
    gate: GovernanceGate | None = None,
    roles: Mapping[str, str] | None = None,
    state_path: str | Path | None = None,
    actions_path: str | Path | None = None,
    at: datetime | None = None,
) -> AssistReport:
    """One unattended pass over the hub. Never raises; a fault becomes a refusal.

    The order is not negotiable: self-test, then read, then clause 5 over the
    whole record, then clauses 1-4 per action, then the gate. Each stage can
    only remove permission. There is no path through this function that reaches
    the gate with a record it could not read, and none that reports an
    executable action without the gate having allowed it.
    """
    at = at or now_utc()
    root = Path(hub)

    probe = selftest()
    if not probe.live:
        return AssistReport(
            decision=Decision.DENY,
            reasons=(
                "the classifier's own self-test is not live, so nothing it says about the "
                "record can be relied on",
                *probe.detail,
            ),
            selftest=probe,
            evaluated_at=at,
        )

    try:
        state, actions = load_hub(root, state_path=state_path, actions_path=actions_path)
    except AssistError as exc:
        return AssistReport(
            decision=Decision.ESCALATE,
            reasons=(
                str(exc),
                "a record that cannot be read is not a record that permits anything",
            ),
            faults=(str(exc),),
            selftest=probe,
            observed=observe(root),
            evaluated_at=at,
        )
    except Exception as exc:  # noqa: BLE001 — deliberate catch-all, same reason as the gate's
        return AssistReport(
            decision=Decision.ESCALATE,
            reasons=(f"unexpected fault reading the hub, refusing: {exc!r}",),
            faults=(repr(exc),),
            selftest=probe,
            evaluated_at=at,
        )

    observed = observe(root)
    faults = list(record_faults(state, actions, root=root))
    if not observed.reachable:
        faults.append(
            "no revision could be observed for this checkout, so no evidence produced here "
            "could be bound to one (AGENTS.md section 9)"
        )

    triage = tuple(classify(a, roles=roles) for a in actions)

    if faults:
        # Every action is reported as REFUSED rather than as classified: the
        # clause-level answers were computed against a record that disagrees
        # with itself, and reporting one of them as executable would be the
        # whole failure mode this module exists to prevent.
        return AssistReport(
            decision=Decision.ESCALATE,
            reasons=(
                f"the record has {len(faults)} fault(s); nothing is executable until a "
                f"person repairs it",
                *faults,
            ),
            triage=tuple(
                Triage(
                    action_id=t.action_id,
                    verdict=REFUSED,
                    clause="record",
                    reasons=("the record as a whole is faulted; see the report's faults",),
                    owner_role=t.owner_role,
                    neuraxis_role=t.neuraxis_role,
                )
                for t in triage
            ),
            faults=tuple(faults),
            selftest=probe,
            state=state,
            observed=observed,
            evaluated_at=at,
        )

    if state.resume_decision != "CONTINUE":
        # The clause-level answers are kept, because "which of these would have
        # been mine, had the hub been resumable" is the useful thing to report
        # to whoever is about to unblock it. But a record-level AGENT_EXECUTABLE
        # is relabelled: this path never reaches the gate, and an action that
        # only one of the two locks has passed is not executable by anyone.
        return AssistReport(
            decision=_DECISION_FOR_RESUME[state.resume_decision],
            reasons=(
                f"the hub's recorded resume decision is {state.resume_decision}; "
                f"an agent does not resume past it",
                *((state.stop_reason[:400],) if state.stop_reason else ()),
            ),
            triage=tuple(_ungated(t, state.resume_decision) for t in triage),
            selftest=probe,
            state=state,
            observed=observed,
            evaluated_at=at,
        )

    gate = gate or GovernanceGate(registry, store)
    decided: list[Triage] = []
    gate_denied = 0
    for item in triage:
        if item.verdict != AGENT_EXECUTABLE:
            decided.append(item)
            continue
        action = next(a for a in actions if a.id == item.action_id)
        verdict = _ask_gate(
            gate,
            state=state,
            action=action,
            role=item.neuraxis_role,
            identity=identity,
            verifier=verifier,
            rollback_tested=rollback_tested,
            at=at,
        )
        if verdict.permits_action:
            decided.append(
                Triage(
                    action_id=item.action_id,
                    verdict=AGENT_EXECUTABLE,
                    clause="record+gate",
                    reasons=(*item.reasons, f"gate: {verdict.decision.value} for {_CAPABILITY}"),
                    owner_role=item.owner_role,
                    neuraxis_role=item.neuraxis_role,
                    gate=verdict.to_dict(),
                )
            )
            continue
        gate_denied += 1
        decided.append(
            Triage(
                action_id=item.action_id,
                verdict=REFUSED,
                clause="gate",
                reasons=(
                    f"the record grants it and the gate does not: {verdict.decision.value}",
                    *verdict.reasons,
                ),
                owner_role=item.owner_role,
                neuraxis_role=item.neuraxis_role,
                gate=verdict.to_dict(),
            )
        )

    executable = [t for t in decided if t.executable]
    if executable:
        decision = Decision.ALLOW
        reasons = (
            f"{len(executable)} of {len(decided)} recorded actions are an unattended agent's "
            f"to perform: {', '.join(t.action_id for t in executable)}",
            "each passed both locks: the record's own clauses and the governance gate",
        )
    elif gate_denied:
        decision = Decision.DENY
        reasons = (
            f"{gate_denied} action(s) the record would grant were refused by the gate",
            "the record's authority does not open a band; the gate does",
        )
    else:
        decision = Decision.WAIT_FOR_AUTHORITY
        reasons = (
            "every recorded action is reserved to a person",
            "nothing here is an unattended agent's to do, which is a finished run, not a failure",
        )

    return AssistReport(
        decision=decision,
        reasons=reasons,
        triage=tuple(decided),
        selftest=probe,
        state=state,
        observed=observed,
        evaluated_at=at,
    )


def _ungated(item: Triage, resume: str) -> Triage:
    """Relabel a record-level grant that never reached the gate."""
    if item.verdict != AGENT_EXECUTABLE:
        return item
    return Triage(
        action_id=item.action_id,
        verdict=REFUSED,
        clause="resume-decision",
        reasons=(
            f"the record grants it, and the hub's resume decision is {resume}, so the gate "
            f"was never asked",
            *item.reasons,
        ),
        owner_role=item.owner_role,
        neuraxis_role=item.neuraxis_role,
    )


_DECISION_FOR_RESUME: Mapping[str, Decision] = {
    "CONTINUE": Decision.ALLOW,
    "WAIT_FOR_AUTHORITY": Decision.WAIT_FOR_AUTHORITY,
    "COMPLETE": Decision.WAIT_FOR_AUTHORITY,
    "BLOCKED": Decision.ESCALATE,
    "RECOVERY_REQUIRED": Decision.ESCALATE,
}


def _ask_gate(
    gate: GovernanceGate,
    *,
    state: HubState,
    action: NextAction,
    role: str,
    identity: str,
    verifier: str | None,
    rollback_tested: bool,
    at: datetime,
) -> Verdict:
    """The second lock. A request the gate cannot even parse is a denial.

    `verifier` and `rollback_tested` are the caller's assertions, defaulted to
    "none" and False so that an assist run configured by nobody is refused by
    NX-INV-2 and NX-INV-3 rather than permitted by them. BAND-B requires both,
    so a run that names no independent verifier gets an empty executable list —
    which is the right answer, not a bug: unattended work whose result nothing
    independent checks is the condition GV-04 exists to rule out.
    """
    try:
        request = AuthorityRequest(
            intent=f"{action.id}: {action.action}"[:300],
            identity=identity,
            role=role,
            capability=_CAPABILITY,
            scope=f"{state.repository or 'biztrust-guide'}#{action.id}",
            verifier=verifier,
            rollback_tested=rollback_tested,
        )
    except ValueError as exc:
        return Verdict(
            decision=Decision.DENY,
            capability=_CAPABILITY,
            band=None,
            reasons=(f"the authority request could not be formed, denying: {exc}",),
            evaluated_at=at,
        )
    return gate.evaluate(request, at=at)
