"""The BizTrust assist agent (v0.20.0).

The thing under test decides what an unattended agent may do to another
repository, so the suite is written from the assumption that it is wrong in the
permissive direction until each clause is shown to hold. Two shapes recur:

  * **the record says yes and the gate must still say no** - the whole point of
    two locks is that either one alone is insufficient, so every gate-refusal
    case is set up with a record that grants the action;
  * **the safe answer arrived for the wrong reason** - a classifier that
    refuses everything passes every deny-assertion below. `test_selftest_*` and
    the positive-control cases exist so that this file cannot pass against one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from neuraxis import (
    AGENT_EXECUTABLE,
    HUMAN_ONLY,
    REFUSED,
    AssistError,
    Decision,
    assist,
    classify,
    load_hub,
)
from neuraxis.biztrust import (
    AUTHORITY_GRANT_PHRASES,
    HUB_ROLE_TO_NEURAXIS,
    HUMAN_SEAT_WORDS,
    NextAction,
    Triage,
    _assert_no_human_seat_in_mapping,
    _git,
    observe,
    selftest,
)
from neuraxis.cli import main

# --- the real hub's own strings, so the suite is about this record ----------

HUB_GRANT = "OPERATOR_INSTRUCTION_2026_09_05_PROCEED_ON_YOUR_CALL_PROPOSED_ONLY"
HUB_RESERVED = "HUMAN_DECISION_REQUIRED"


def _action(**kw) -> NextAction:
    """An action that is agent-executable in every clause, before kw is applied.

    The positive control for every clause test below: each one changes exactly
    one field, so a HUMAN_ONLY answer is attributable to that field and not to
    a fixture that was never executable.
    """
    base = dict(
        id="NS-900",
        action="Regenerate the control page from its recorded fixture.",
        owner_role="documentation-engineer",
        authority=HUB_GRANT,
        primary=True,
        priority=1,
        evidence_required=("The runner's output attached to the pull request",),
        stop_conditions=("The fixture cannot be rebuilt from the recorded baseline",),
    )
    base.update(kw)
    return NextAction(**base)


# ---------------------------------------------------------------------------
# The self-test. Everything else in this file is meaningless without it.
# ---------------------------------------------------------------------------


def test_selftest_is_live_on_the_shipped_constants():
    probe = selftest()
    assert probe.live, probe.detail
    assert probe.positive_control and probe.vacuity_probe


def test_positive_control_fails_when_the_grant_vocabulary_is_emptied(monkeypatch):
    """A classifier that refuses everything must report itself broken.

    This is the failure the first cut of AUTHORITY_VETO_TOKENS actually had,
    and it is invisible to every deny-assertion in this file.
    """
    monkeypatch.setattr("neuraxis.biztrust.AUTHORITY_GRANT_PHRASES", ())
    probe = selftest()
    assert not probe.live
    assert not probe.positive_control
    assert probe.vacuity_probe, "the vacuity probe should still pass; only the grant path broke"
    assert any("refuses everything" in d for d in probe.detail)


def test_vacuity_probe_fails_when_every_veto_is_removed(monkeypatch):
    monkeypatch.setattr("neuraxis.biztrust.AUTHORITY_VETO_TOKENS", frozenset())
    monkeypatch.setattr("neuraxis.biztrust.AUTHORITY_VETO_STEMS", ())
    monkeypatch.setattr(
        "neuraxis.biztrust.HUB_ROLE_TO_NEURAXIS", {"human-reviewer": "drafter", **HUB_ROLE_TO_NEURAXIS}
    )
    monkeypatch.setattr("neuraxis.biztrust.AGENT_WORDS", ())
    monkeypatch.setattr("neuraxis.biztrust.HUMAN_EVIDENCE_PHRASES", ())
    monkeypatch.setattr(
        "neuraxis.biztrust.AUTHORITY_GRANT_PHRASES", (("HUMAN",), *AUTHORITY_GRANT_PHRASES)
    )
    probe = selftest()
    assert not probe.live
    assert not probe.vacuity_probe
    assert any("discriminates nothing" in d for d in probe.detail)


def test_a_run_whose_selftest_is_not_live_permits_nothing(monkeypatch, tmp_path, registry, full_store):
    hub = _hub(tmp_path, resume="CONTINUE")
    monkeypatch.setattr("neuraxis.biztrust.AUTHORITY_GRANT_PHRASES", ())
    report = assist(
        hub, registry=registry, store=full_store, verifier="github-ci", rollback_tested=True
    )
    assert report.decision is Decision.DENY
    assert report.executable == ()
    assert "self-test is not live" in report.reasons[0]


# ---------------------------------------------------------------------------
# Clause 1 - authority
# ---------------------------------------------------------------------------


def test_the_hubs_real_grant_is_agent_executable():
    """The positive control at clause level. Without it every case below is vacuous."""
    assert classify(_action()).verdict == AGENT_EXECUTABLE


def test_human_decision_required_is_reserved():
    triage = classify(_action(authority=HUB_RESERVED))
    assert triage.verdict == HUMAN_ONLY
    assert triage.clause == "authority"
    assert "HUMAN" in triage.reasons[0]


def test_absent_authority_is_not_a_grant():
    triage = classify(_action(authority="   "))
    assert triage.verdict == HUMAN_ONLY
    assert "no authority" in triage.reasons[0]


def test_a_veto_token_is_not_outvoted_by_a_grant_phrase():
    """`PROCEED_ON_YOUR_CALL_PENDING_RATIFICATION` is not permission to proceed."""
    triage = classify(_action(authority="PROCEED_ON_YOUR_CALL_PENDING_RATIFICATION"))
    assert triage.verdict == HUMAN_ONLY
    assert "does not outvote" in " ".join(triage.reasons)


def test_negation_cannot_be_spelled_around():
    for authority in (
        "NOT_PROCEED_ON_YOUR_CALL",
        "AUTHORITY_NOT_YET_GRANTED_TO_AGENT",
        "PROCEED-ON-YOUR-CALL-WHEN-APPROVED",
    ):
        assert classify(_action(authority=authority)).verdict == HUMAN_ONLY, authority


def test_an_inflection_does_not_escape_a_veto():
    """The exact-token set was defeated by `APPROVED`; the stems close it.

    A grant conditional on something that has not happened yet is not a grant,
    however the condition is conjugated.
    """
    for authority in (
        "PROCEED_ON_YOUR_CALL_ONCE_APPROVED",
        "PROCEED_ON_YOUR_CALL_AFTER_RATIFICATION",
        "PROCEED_ON_YOUR_CALL_PENDING_REVIEW",
        "PROCEED_ON_YOUR_CALL_UNLESS_REVOKED",
        "PROCEED_ON_YOUR_CALL_WHEN_THE_WAIVER_IS_SIGNED",
        "PROCEED_ON_YOUR_CALL_ESCALATION_FIRST",
    ):
        assert classify(_action(authority=authority)).verdict == HUMAN_ONLY, authority


def test_a_stem_does_not_swallow_an_unrelated_word():
    """`NO` is not a stem, because a veto list that refuses `PROCEED_NOW` is the
    over-refusal the vacuity probe exists to catch."""
    assert classify(_action(authority="PROCEED_ON_YOUR_CALL_NOW")).verdict == AGENT_EXECUTABLE


def test_punctuation_does_not_change_the_answer():
    """The token stream is separator-blind, so a grant cannot be smuggled in by spelling."""
    for spelling in (
        "proceed on your call",
        "PROCEED-ON-YOUR-CALL",
        "operator.instruction/proceed_on_your_call",
    ):
        assert classify(_action(authority=spelling)).verdict == AGENT_EXECUTABLE, spelling


def test_an_unrecognised_authority_string_is_not_read_generously():
    """Two real strings from the hub that no grant phrase matches.

    Under-matching is the safe direction: the remedy is for the hub to adopt a
    canonical grant phrase, not for this module to guess at new ones.
    """
    for authority in (
        "OPERATOR_INSTRUCTION_2026_09_06_PROCEED_PROPOSED_ONLY",
        "OPERATOR_INSTRUCTION_2026_09_06_CONTINUE_ON_THE_TRACK_AS_RECOMMENDED_PROPOSED_ONLY",
        "GRANTED_BY_USER_REQUEST_2026_09_03",
    ):
        triage = classify(_action(authority=authority))
        assert triage.verdict == HUMAN_ONLY, authority
        assert "no grant phrase" in triage.reasons[0]


# ---------------------------------------------------------------------------
# Clause 2 - the seat
# ---------------------------------------------------------------------------


def test_a_human_seat_is_never_an_agents_even_under_a_grant():
    for role in ("human-reviewer", "architecture-owner", "business-authority"):
        triage = classify(_action(owner_role=role))
        assert triage.verdict == HUMAN_ONLY, role
        assert triage.clause == "seat"


def test_an_unmapped_role_has_no_neuraxis_role_and_never_reaches_the_gate():
    triage = classify(_action(owner_role="release-manager"))
    assert triage.verdict == HUMAN_ONLY
    assert triage.neuraxis_role == ""


def test_a_caller_may_narrow_the_role_mapping_and_may_not_widen_it():
    widened = {**HUB_ROLE_TO_NEURAXIS, "human-reviewer": "operator"}
    triage = classify(_action(owner_role="human-reviewer"), roles=widened)
    assert triage.verdict == HUMAN_ONLY

    narrowed = {"documentation-engineer": "drafter"}
    assert classify(_action(), roles=narrowed).verdict == AGENT_EXECUTABLE
    assert classify(_action(owner_role="continuity-engineer"), roles=narrowed).verdict == HUMAN_ONLY


def test_a_caller_may_not_rename_the_role_a_hub_role_maps_onto():
    """`{"documentation-engineer": "operator"}` is a privilege escalation, not a narrowing."""
    triage = classify(_action(), roles={"documentation-engineer": "operator"})
    assert triage.verdict == HUMAN_ONLY


def test_the_shipped_mapping_names_no_human_seat():
    _assert_no_human_seat_in_mapping()
    for hub_role in HUB_ROLE_TO_NEURAXIS:
        assert not any(word in hub_role.lower() for word in HUMAN_SEAT_WORDS)


def test_adding_a_human_seat_to_the_mapping_is_refused(monkeypatch):
    monkeypatch.setattr(
        "neuraxis.biztrust.HUB_ROLE_TO_NEURAXIS", {"human-reviewer": "drafter"}
    )
    with pytest.raises(AssistError, match="human seat"):
        _assert_no_human_seat_in_mapping()


# ---------------------------------------------------------------------------
# Clause 3 - stop conditions
# ---------------------------------------------------------------------------


def test_the_hubs_own_stop_conditions_reserve_their_actions():
    for condition in (
        "An agent posts the waiver, or a chat instruction is treated as the waiver (DEC-043)",
        "An agent supplies either answer",
        "An agent occupies or infers a seat",
        "Automation merges the change",
    ):
        triage = classify(_action(stop_conditions=(condition,)))
        assert triage.verdict == HUMAN_ONLY, condition
        assert triage.clause == "stop-condition"


def test_an_agent_word_inside_another_word_does_not_fire():
    """Over-broad on purpose, but not arbitrary: the match is on whole words."""
    triage = classify(_action(stop_conditions=("The reagent register is stale",)))
    assert triage.verdict == AGENT_EXECUTABLE


def test_a_later_stop_condition_is_read_too():
    triage = classify(
        _action(stop_conditions=("The fixture is missing", "An agent closes the ticket"))
    )
    assert triage.verdict == HUMAN_ONLY


# ---------------------------------------------------------------------------
# Clause 4 - evidence
# ---------------------------------------------------------------------------


def test_evidence_only_a_person_can_produce_reserves_the_action():
    for requirement in (
        "A comment on #27 with no agent marker stating the waiver's scope",
        "A written answer per tenant, recorded on #93",
        "Five rows on #94, one per seat",
        "A human reads issue #78",
    ):
        triage = classify(_action(evidence_required=(requirement,)))
        assert triage.verdict == HUMAN_ONLY, requirement
        assert triage.clause == "evidence"


def test_an_evidence_phrase_inside_another_word_does_not_fire():
    """`signed` must not fire inside `designed`.

    Over-refusing is the cheap direction, but an over-refusal nobody can
    explain from the text reads as a bug, and the report has to be able to
    name the phrase it matched.
    """
    triage = classify(
        _action(evidence_required=("The designed output, attached to the pull request",))
    )
    assert triage.verdict == AGENT_EXECUTABLE


def test_an_action_evidencing_nothing_is_not_unattended_work():
    triage = classify(_action(evidence_required=()))
    assert triage.verdict == HUMAN_ONLY
    assert triage.clause == "evidence"


# ---------------------------------------------------------------------------
# The record as a whole (clause 5)
# ---------------------------------------------------------------------------


def _write_hub(
    root: Path,
    *,
    state: dict,
    actions: dict,
    checkpoint: bool = True,
    git: bool = True,
) -> Path:
    (root / "badf").mkdir(parents=True, exist_ok=True)
    (root / "badf" / "current-state.json").write_text(json.dumps(state), encoding="utf-8")
    (root / "badf" / "next-actions.json").write_text(json.dumps(actions), encoding="utf-8")
    if checkpoint:
        target = root / str(state.get("latest_checkpoint") or "sessions/cp.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    if git:
        _git_init(root)
    return root


def _git_init(root: Path) -> None:
    def run(*args: str) -> int:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, check=False
            ).returncode
        except (OSError, subprocess.SubprocessError):
            pytest.skip("git is not available")
            return 1

    if run("init", "--quiet") != 0:
        pytest.skip("git init failed in this environment")
    run("config", "user.email", "suite@example.invalid")
    run("config", "user.name", "suite")
    run("add", "-A")
    if run("commit", "--quiet", "-m", "fixture") != 0:
        pytest.skip("git commit failed in this environment")


def _state(**kw) -> dict:
    base = {
        "schema_version": "1.0.0",
        "project_id": "BIZTRUST-GUIDE",
        "repository": "bstBizEra/biztrust_guide",
        "updated_at": "2026-09-10T20:00:00Z",
        "active_work_package": {
            "id": "WP-900",
            "state": "IN_PROGRESS",
            "scope": ["scripts/control_harness.py"],
        },
        "source": {"branch": "main", "baseline_commit": "0" * 40},
        "latest_checkpoint": "sessions/cp.json",
        "primary_next_action_id": "NS-900",
        "resume_decision": "CONTINUE",
    }
    base.update(kw)
    return base


def _actions(*entries: dict, work_package_id: str = "WP-900") -> dict:
    if not entries:
        entries = ({
            "id": "NS-900",
            "primary": True,
            "priority": 1,
            "owner_role": "documentation-engineer",
            "authority": HUB_GRANT,
            "action": "Regenerate the control page from its recorded fixture.",
            "evidence_required": ["The runner's output attached to the pull request"],
            "stop_conditions": ["The fixture cannot be rebuilt from the recorded baseline"],
        },)
    return {
        "schema_version": "1.0.0",
        "project_id": "BIZTRUST-GUIDE",
        "work_package_id": work_package_id,
        "updated_at": "2026-09-10T20:00:00Z",
        "actions": list(entries),
    }


def _hub(tmp_path: Path, *, resume: str = "CONTINUE", **kw) -> Path:
    root = tmp_path / "hub"
    return _write_hub(root, state=_state(resume_decision=resume, **kw), actions=_actions())


def _report(hub, registry, store, **kw):
    params = dict(verifier="github-ci", rollback_tested=True)
    params.update(kw)
    return assist(hub, registry=registry, store=store, **params)


def test_the_two_files_must_name_the_same_work_package(tmp_path):
    root = _write_hub(
        tmp_path / "hub", state=_state(), actions=_actions(work_package_id="WP-901")
    )
    with pytest.raises(AssistError, match="different work packages"):
        load_hub(root)


def test_malformed_json_refuses_rather_than_reporting_nothing(tmp_path, registry, full_store):
    root = _hub(tmp_path)
    (root / "badf" / "next-actions.json").write_text("{not json", encoding="utf-8")
    report = _report(root, registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert report.executable == ()
    assert report.faults


def test_a_missing_file_refuses(tmp_path, registry, full_store):
    root = _hub(tmp_path)
    (root / "badf" / "current-state.json").unlink()
    report = _report(root, registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert report.executable == ()


def test_an_empty_action_list_is_not_a_plan(tmp_path):
    root = _write_hub(
        tmp_path / "hub", state=_state(), actions={**_actions(), "actions": []}
    )
    with pytest.raises(AssistError, match="empty"):
        load_hub(root)


def test_a_top_level_array_is_refused(tmp_path):
    root = _hub(tmp_path)
    (root / "badf" / "next-actions.json").write_text("[]", encoding="utf-8")
    with pytest.raises(AssistError, match="top level"):
        load_hub(root)


def test_primary_must_be_a_boolean(tmp_path):
    entry = _actions()["actions"][0] | {"primary": "false"}
    root = _write_hub(tmp_path / "hub", state=_state(), actions=_actions(entry))
    with pytest.raises(AssistError, match="JSON boolean"):
        load_hub(root)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda s, a: s.update(primary_next_action_id="NS-999"), "names no action"),
        (
            lambda s, a: a["actions"].append(
                {**a["actions"][0], "id": "NS-901", "priority": 2, "primary": True}
            ),
            "exactly one action must be primary",
        ),
        (
            lambda s, a: a["actions"].append(
                {**a["actions"][0], "id": "NS-901", "priority": 7, "primary": False}
            ),
            "priorities must be",
        ),
        (
            lambda s, a: a["actions"].append({**a["actions"][0], "priority": 2, "primary": False}),
            "duplicate action id",
        ),
        (lambda s, a: s.update(resume_decision="PROCEED"), "not in a known state"),
        (lambda s, a: s.update(latest_checkpoint=""), "no latest_checkpoint"),
        (lambda s, a: s.update(latest_checkpoint="sessions/absent.json"), "not a file"),
        (
            lambda s, a: s["source"].update(baseline_commit="deadbeef"),
            "not a 40-character sha",
        ),
    ],
)
def test_a_faulted_record_poisons_the_whole_run(tmp_path, registry, full_store, mutate, expected):
    state, actions = _state(), _actions()
    mutate(state, actions)
    # The checkpoint is written at the path the UNMUTATED record named, so the
    # "record names a checkpoint that is not here" case is a real absence.
    root = _write_hub(
        tmp_path / "hub", state=state, actions=actions, checkpoint=False, git=False
    )
    cp = root / "sessions" / "cp.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text("{}", encoding="utf-8")
    _git_init(root)
    report = _report(root, registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert report.executable == ()
    assert any(expected in f for f in report.faults), report.faults
    # The action that would otherwise have been executable is refused, not kept.
    assert {t.verdict for t in report.triage} == {REFUSED}


def test_a_checkout_with_no_observable_revision_binds_no_evidence(tmp_path, registry, full_store):
    root = _write_hub(tmp_path / "hub", state=_state(), actions=_actions(), git=False)
    report = _report(root, registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert report.executable == ()
    assert any("no revision could be observed" in f for f in report.faults)


def test_the_hubs_own_resume_decision_stops_the_run(tmp_path, registry, full_store):
    for resume, decision in (
        ("WAIT_FOR_AUTHORITY", Decision.WAIT_FOR_AUTHORITY),
        ("COMPLETE", Decision.WAIT_FOR_AUTHORITY),
        ("BLOCKED", Decision.ESCALATE),
        ("RECOVERY_REQUIRED", Decision.ESCALATE),
    ):
        report = _report(_hub(tmp_path / resume, resume=resume), registry, full_store)
        assert report.decision is decision, resume
        assert report.executable == ()
        # The record-level grant is relabelled, because the gate was never asked.
        assert [t.verdict for t in report.triage] == [REFUSED]
        assert report.triage[0].clause == "resume-decision"


# ---------------------------------------------------------------------------
# The second lock
# ---------------------------------------------------------------------------


def test_the_record_alone_does_not_open_a_band(tmp_path, registry, empty_store):
    """The load-bearing case: a record that grants, a gate with nothing attested."""
    report = _report(_hub(tmp_path), registry, empty_store)
    assert report.decision is Decision.DENY
    assert report.executable == ()
    refused = report.triage[0]
    assert refused.verdict == REFUSED and refused.clause == "gate"
    assert refused.gate and refused.gate["decision"] != "ALLOW"


def test_both_locks_open_it(tmp_path, registry, full_store):
    report = _report(_hub(tmp_path), registry, full_store)
    assert report.decision is Decision.ALLOW
    assert [t.action_id for t in report.executable] == ["NS-900"]
    assert report.executable[0].clause == "record+gate"
    assert report.executable[0].gate["decision"] == "ALLOW"


def test_naming_no_verifier_refuses_everything(tmp_path, registry, full_store):
    report = _report(_hub(tmp_path), registry, full_store, verifier=None)
    assert report.decision is Decision.DENY
    assert report.executable == ()
    assert any("verifier" in r for r in report.triage[0].reasons)


def test_an_agent_may_not_verify_itself(tmp_path, registry, full_store):
    report = _report(
        _hub(tmp_path), registry, full_store, identity="nx-assist", verifier="nx-assist"
    )
    assert report.decision is Decision.DENY
    assert any("NX-INV-2" in r for r in report.triage[0].reasons)


def test_an_untested_rollback_counts_as_none(tmp_path, registry, full_store):
    report = _report(_hub(tmp_path), registry, full_store, rollback_tested=False)
    assert report.decision is Decision.DENY
    assert any("NX-INV-3" in r for r in report.triage[0].reasons)


def test_a_triage_with_no_gate_answer_is_never_executable():
    """Defence in depth: the property, not only the code paths that build it."""
    assert not Triage(
        action_id="NS-900", verdict=AGENT_EXECUTABLE, clause="record", reasons=()
    ).executable
    assert not Triage(
        action_id="NS-900",
        verdict=AGENT_EXECUTABLE,
        clause="record+gate",
        reasons=(),
        gate={"decision": "DENY"},
    ).executable
    assert Triage(
        action_id="NS-900",
        verdict=AGENT_EXECUTABLE,
        clause="record+gate",
        reasons=(),
        gate={"decision": "ALLOW"},
    ).executable


def test_a_human_only_action_never_reaches_the_gate(tmp_path, registry, full_store):
    entry = _actions()["actions"][0] | {"authority": HUB_RESERVED}
    root = _write_hub(tmp_path / "hub", state=_state(), actions=_actions(entry))
    report = _report(root, registry, full_store)
    assert report.decision is Decision.WAIT_FOR_AUTHORITY
    assert report.triage[0].gate is None
    assert report.executable == ()


# ---------------------------------------------------------------------------
# No write path
# ---------------------------------------------------------------------------


def test_git_is_restricted_to_a_read_only_allowlist(tmp_path):
    for forbidden in ("commit", "push", "checkout", "reset", "config"):
        with pytest.raises(AssistError, match="read-only allowlist"):
            _git(tmp_path, forbidden)


def test_the_module_holds_no_write_api(tmp_path):
    """A ratchet, not a proof: the mechanism is the git allowlist above.

    It catches the change nobody means to make - a convenience `write_text` in
    a helper - at review time rather than after an agent has edited the hub.
    """
    source = Path(__import__("neuraxis.biztrust", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("write_text(", "mkdir(", "unlink(", "rmtree(", "os.remove", "shutil."):
        assert forbidden not in body, f"{forbidden} appeared in biztrust.py"


def test_observe_reports_an_unreadable_checkout_as_a_fact(tmp_path):
    seen = observe(tmp_path / "nothing-here")
    assert not seen.reachable
    assert seen.head == ""


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_cli_self_test_exits_zero():
    assert main(["assist", "--self-test"]) == 0


def test_cli_self_test_reports_a_broken_classifier(monkeypatch, capsys):
    monkeypatch.setattr("neuraxis.biztrust.AUTHORITY_GRANT_PHRASES", ())
    assert main(["assist", "--self-test"]) == 2
    assert "NOT LIVE" in capsys.readouterr().out


def test_cli_exit_codes_follow_the_decision(tmp_path, capsys):
    hub = _hub(tmp_path)
    # Nothing attested: the record grants, the gate does not. 10 = DENY.
    assert main(
        ["--attestations", str(tmp_path / "absent.jsonl"), "assist",
         "--hub", str(hub), "--verifier", "github-ci", "--rollback-tested"]
    ) == 10

    # The hub itself is waiting: 12, and it is a finished run.
    waiting = _hub(tmp_path / "waiting", resume="WAIT_FOR_AUTHORITY")
    assert main(
        ["--attestations", str(tmp_path / "absent.jsonl"), "assist",
         "--hub", str(waiting), "--verifier", "github-ci"]
    ) == 12
    assert "nothing here is an unattended agent's to do" in capsys.readouterr().out


def test_cli_json_is_machine_readable(tmp_path, capsys):
    hub = _hub(tmp_path)
    main(
        ["--attestations", str(tmp_path / "absent.jsonl"), "--json", "assist",
         "--hub", str(hub), "--verifier", "github-ci"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "DENY"
    assert payload["executable"] == []
    assert payload["selftest"]["live"] is True
    assert payload["state"]["work_package_id"] == "WP-900"
    assert len(payload["triage"]) == 1


# ---------------------------------------------------------------------------
# The fail-closed branches. Each of these is a path that exists so that a
# malformed record produces a refusal rather than a traceback a caller could
# read as "no findings" - so each is worth a test of its own.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actions, expected",
    [
        ({"actions": ["not an object"]}, "expected an object"),
        ({"actions": [{"id": "NS-1", "action": "x", "owner_role": "", "authority": "y"}]},
         "missing or empty"),
        ({"actions": [{"id": "NS-1", "action": "x", "owner_role": "r", "authority": "y",
                       "priority": "1"}]}, "priority must be an integer"),
        ({"actions": [{"id": "NS-1", "action": "x", "owner_role": "r", "authority": "y",
                       "prerequisites": "not a list"}]}, "expected an array of strings"),
        ({"actions": [{"id": "NS-1", "action": "x", "owner_role": "r", "authority": "y",
                       "stop_conditions": [7]}]}, "expected a string"),
        ({"actions": "not an array"}, "is absent or is not an array"),
    ],
)
def test_a_wrong_typed_field_is_a_refusal_not_a_traceback(tmp_path, actions, expected):
    root = _write_hub(
        tmp_path / "hub", state=_state(), actions={**_actions(), **actions}, git=False
    )
    with pytest.raises(AssistError, match=expected):
        load_hub(root)


@pytest.mark.parametrize(
    "state, expected",
    [
        ({"active_work_package": None}, "absent or not an object"),
        ({"active_work_package": "WP-900"}, "absent or not an object"),
    ],
)
def test_a_state_file_without_a_work_package_object_is_refused(tmp_path, state, expected):
    root = _write_hub(
        tmp_path / "hub", state={**_state(), **state}, actions=_actions(),
        checkpoint=False, git=False,
    )
    with pytest.raises(AssistError, match=expected):
        load_hub(root)


def test_a_state_file_that_is_not_an_object_is_refused(tmp_path):
    root = _hub(tmp_path)
    (root / "badf" / "current-state.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(AssistError, match="top level"):
        load_hub(root)


def test_an_action_without_a_priority_faults_the_record(tmp_path, registry, full_store):
    entry = {k: v for k, v in _actions()["actions"][0].items() if k != "priority"}
    root = _write_hub(tmp_path / "hub", state=_state(), actions=_actions(entry))
    report = _report(root, registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert any("must carry a priority" in f for f in report.faults)


def test_an_unexpected_fault_while_reading_denies(tmp_path, monkeypatch, registry, full_store):
    """The catch-all. An exception nobody foresaw must not reach the caller as silence."""
    def explode(*_args, **_kw):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr("neuraxis.biztrust.load_hub", explode)
    report = _report(_hub(tmp_path), registry, full_store)
    assert report.decision is Decision.ESCALATE
    assert report.executable == ()
    assert "something nobody anticipated" in report.reasons[0]


def test_a_request_the_gate_cannot_parse_is_a_denial(tmp_path, registry, full_store):
    """`performer="   "` is the shape: a request that raises on construction.

    Here it is provoked with a blank identity, which `AuthorityRequest` refuses.
    A construction failure must become a DENY, never an exception that skips the
    gate entirely.
    """
    report = _report(_hub(tmp_path), registry, full_store, identity="   ")
    assert report.decision is Decision.DENY
    assert report.executable == ()
    assert any("could not be formed" in r for r in report.triage[0].reasons)


def test_report_json_round_trips(tmp_path, registry, full_store):
    report = _report(_hub(tmp_path), registry, full_store)
    payload = json.loads(report.to_json())
    assert payload["decision"] == "ALLOW"
    assert payload["observed"]["reachable"] is True
    assert report.permits_action


def test_permits_action_requires_an_executable_action(tmp_path, registry, full_store):
    waiting = _report(_hub(tmp_path, resume="COMPLETE"), registry, full_store)
    assert not waiting.permits_action


def test_git_that_cannot_run_is_reported_rather_than_raised(tmp_path, monkeypatch):
    def explode(*_args, **_kw):
        raise OSError("no git on this machine")

    monkeypatch.setattr("neuraxis.biztrust.subprocess.run", explode)
    assert not observe(tmp_path).reachable
