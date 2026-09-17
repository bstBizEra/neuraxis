"""The build sequence as a dependency graph (v0.14.0).

The roadmap is the one artefact in this repository that nothing enforced. These
tests are mostly about the ways a plan can look green while being wrong: a
declared state nobody checked, a blocker that is a string rather than a
dependency, an external nobody owns, and a gate that silently vanished because
a YAML key was written twice.
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from neuraxis import AttestationStore, load_registry, load_roadmap
from neuraxis.cli import main
from neuraxis.roadmap import (
    BLOCKED,
    GATE_KINDS,
    ITEM_STATES,
    READY,
    UNKNOWN,
    RoadmapError,
)

_MINIMAL = """
version: 1
roadmap: test
externals:
  EXT-A:
    title: Something someone else owns
    owner: somebody
    attained: false
items:
  - id: A
    title: First
    state: planned
    owner: me
    ungated_because: a fixture that waits on nothing
"""


def _write(tmp_path, body: str):
    path = tmp_path / "roadmap.yaml"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


def _resolved(tmp_path, body: str, *, with_gate: bool = False, **kw):
    roadmap = load_roadmap(_write(tmp_path, body))
    if with_gate:
        return roadmap.resolve(load_registry(), AttestationStore(), **kw)
    return roadmap.resolve(**kw)


def _by_id(report):
    return {r.item.id: r for r in report.items}


# ---- the shipped roadmap ------------------------------------------------


def test_the_shipped_roadmap_loads():
    roadmap = load_roadmap()
    assert roadmap.items and roadmap.externals


def test_the_shipped_roadmap_contradicts_itself_nowhere():
    """A regression guard with teeth.

    If someone marks an item shipped while its gates are unsatisfied, this
    fails - which is the whole point of computing readiness rather than reading
    a status column.
    """
    report = load_roadmap().resolve(load_registry(), AttestationStore())
    assert report.contradictions == (), [r.contradiction for r in report.contradictions]


def test_every_declared_external_is_actually_waited_on():
    """An external nobody waits on is dead weight that reads as a real blocker."""
    roadmap = load_roadmap()
    waited = {
        g.id for item in roadmap.items.values() for g in item.gates if g.kind == "external"
    }
    assert set(roadmap.externals) == waited, set(roadmap.externals) ^ waited


def test_the_freeze_is_in_force_and_says_what_lifts_it():
    report = load_roadmap().resolve(load_registry(), AttestationStore())
    assert report.freeze_in_force is True
    assert report.freeze_reasons
    assert "caller-conform" in load_roadmap().freeze["operative_definition"]


# ---- the loader refuses what it cannot depend on ------------------------


def test_a_duplicate_key_is_refused_rather_than_silently_overwritten(tmp_path):
    """The bug this file was written after.

    PyYAML takes the last mapping key. An item carrying `gates: []` and a real
    `gates:` block loses the empty one silently - or, written the other way
    round, loses every gate and reports READY.
    """
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - id: A
                title: First
                state: planned
                owner: me
                gates: []
                gates:
                  - kind: item
                    id: A
        """))
    assert "duplicate key" in str(exc.value)


def test_an_external_with_no_owner_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            externals:
              EXT-A: {title: x, attained: false}
            items: []
        """))
    assert "wish" in str(exc.value)


def test_attained_must_be_a_boolean_not_a_word(tmp_path):
    """`attained: "false"` is a non-empty string and therefore truthy."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            externals:
              EXT-A: {title: x, owner: somebody, attained: "false"}
            items: []
        """))
    assert "boolean" in str(exc.value)


def test_a_gate_naming_a_missing_item_is_a_load_failure(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - id: A
                title: First
                state: planned
                owner: me
                gates: [{kind: item, id: NOPE}]
        """))
    assert "does not exist" in str(exc.value)


def test_a_gate_naming_an_undeclared_external_is_a_load_failure(tmp_path):
    """Otherwise a typo becomes a permanent mystery blocker.

    An undeclared external would evaluate to UNKNOWN, which blocks - safe, and
    indistinguishable from a real unknown nobody can chase.
    """
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - id: A
                title: First
                state: planned
                owner: me
                gates: [{kind: external, id: T9}]
        """))
    assert "not declared" in str(exc.value)


def test_a_cycle_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - {id: A, title: A, state: planned, owner: me, gates: [{kind: item, id: B}]}
              - {id: B, title: B, state: planned, owner: me, gates: [{kind: item, id: A}]}
        """))
    assert "cycle" in str(exc.value)


def test_an_item_with_no_owner_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: planned, ungated_because: x}]
        """))
    assert "nobody owns" in str(exc.value)


def test_an_unknown_state_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: nearly, owner: me, ungated_because: x}]
        """))
    assert "nearly" in str(exc.value)
    assert all(s in str(exc.value) for s in ITEM_STATES)


def test_a_command_given_as_a_string_is_refused_not_split(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - id: A
                title: A
                state: planned
                owner: me
                gates: [{kind: command, run: "python C:\\\\x\\\\y.py"}]
        """))
    assert "argv" in str(exc.value)


def test_a_frozen_roadmap_must_say_what_lifts_the_freeze(tmp_path):
    """A freeze that cannot be discharged is one that gets ignored instead."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            freeze: {id: F, in_force: true}
            items: [{id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}]
        """))
    assert "lift condition" in str(exc.value)


def test_a_freeze_naming_a_missing_item_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            freeze: {id: F, in_force: true, lifts_when: [{kind: item, id: GHOST}]}
            items: [{id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}]
        """))
    assert "GHOST" in str(exc.value)


# ---- unknown blocks -----------------------------------------------------


def test_an_unrecognised_gate_kind_blocks_rather_than_vanishing(tmp_path):
    """A gate a newer roadmap introduces must block an older tool.

    The alternative is that it disappears from the evaluation, and an item
    reports READY on a condition this version cannot even read.
    """
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: moon_phase, id: full}]}
    """)
    item = _by_id(report)["A"]
    assert item.verdict == UNKNOWN
    assert not item.actionable
    assert "moon_phase" in item.gates[0].detail
    assert all(k in item.gates[0].detail for k in GATE_KINDS)


def test_a_band_gate_with_no_registry_is_unknown_not_ready(tmp_path):
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: band_attained, id: BAND-A}]}
    """)
    assert _by_id(report)["A"].verdict == UNKNOWN


def test_a_band_not_in_the_registry_is_unknown_not_a_crash(tmp_path):
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: band_attained, id: BAND-Z}]}
    """, with_gate=True)
    item = _by_id(report)["A"]
    assert item.verdict == UNKNOWN
    assert "not a band" in item.gates[0].detail


def test_a_command_gate_is_unknown_until_it_is_run(tmp_path):
    body = """
        version: 1
        roadmap: test
        items:
          - id: A
            title: A
            state: planned
            owner: me
            gates: [{kind: command, run: ["%s", "-c", "pass"]}]
    """ % sys.executable.replace("\\", "\\\\")
    assert _by_id(_resolved(tmp_path, body))["A"].verdict == UNKNOWN
    assert _by_id(_resolved(tmp_path, body, run_commands=True))["A"].verdict == READY


def test_a_failing_command_gate_blocks(tmp_path):
    body = """
        version: 1
        roadmap: test
        items:
          - id: A
            title: A
            state: planned
            owner: me
            gates: [{kind: command, run: ["%s", "-c", "raise SystemExit(3)"]}]
    """ % sys.executable.replace("\\", "\\\\")
    item = _by_id(_resolved(tmp_path, body, run_commands=True))["A"]
    assert item.verdict == BLOCKED
    assert "exit 3" in item.gates[0].detail


def test_a_missing_command_blocks_rather_than_raising(tmp_path):
    item = _by_id(_resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: command, run: ["no-such-binary-xyz"]}]}
    """, run_commands=True))["A"]
    assert item.verdict == BLOCKED
    assert "not found" in item.gates[0].detail


def test_a_hanging_command_gate_has_not_passed(tmp_path):
    body = """
        version: 1
        roadmap: test
        items:
          - id: A
            title: A
            state: planned
            owner: me
            gates: [{kind: command, run: ["%s", "-c", "import time; time.sleep(30)"]}]
    """ % sys.executable.replace("\\", "\\\\")
    item = _by_id(_resolved(tmp_path, body, run_commands=True, timeout=1.0))["A"]
    assert item.verdict == BLOCKED
    assert "timed out" in item.gates[0].detail


# ---- a declared state is a claim ----------------------------------------


def test_a_shipped_item_with_an_unsatisfied_gate_is_a_contradiction(tmp_path):
    """The shape of 'the Band C work shipped while Band C was blocked'."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        externals:
          T1: {title: kernel, owner: somebody, attained: false}
        items:
          - {id: A, title: A, state: shipped, owner: me, gates: [{kind: external, id: T1}]}
    """)
    item = _by_id(report)["A"]
    assert item.contradiction
    assert report.contradictions == (item,)
    assert "not done or the gate never applied" in item.contradiction


def test_a_shipped_item_is_never_actionable(tmp_path):
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items: [{id: A, title: A, state: shipped, owner: me, ungated_because: nothing gates it}]
    """)
    assert _by_id(report)["A"].verdict == READY
    assert not _by_id(report)["A"].actionable
    assert report.actionable == ()


def test_an_item_gate_is_satisfied_by_shipped_not_by_ready(tmp_path):
    """B waits on A. A is unblocked but unbuilt, so B still waits."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}
          - {id: B, title: B, state: planned, owner: me, gates: [{kind: item, id: A}]}
    """)
    items = _by_id(report)
    assert items["A"].actionable
    assert items["B"].verdict == BLOCKED
    assert "not shipped" in items["B"].gates[0].detail


def test_acceptance_runs_only_for_work_that_claims_to_have_shipped(tmp_path):
    """A command attached to unbuilt work proves nothing, so it is not run."""
    failing = json.dumps([sys.executable, "-c", "raise SystemExit(1)"])
    report = _resolved(tmp_path, f"""
        version: 1
        roadmap: test
        items:
          - id: PLANNED
            title: not built yet
            state: planned
            owner: me
            ungated_because: nothing gates it
            acceptance: [{{run: {failing}}}]
          - id: SHIPPED
            title: claims to be in
            state: shipped
            owner: me
            ungated_because: nothing gates it
            acceptance: [{{run: {failing}}}]
    """, run_commands=True)
    items = _by_id(report)
    assert items["PLANNED"].acceptance == ()
    assert not items["PLANNED"].contradiction
    assert items["SHIPPED"].acceptance and not items["SHIPPED"].acceptance[0].satisfied
    assert "its own acceptance fails" in items["SHIPPED"].contradiction


def test_a_partial_item_is_held_to_its_acceptance_too(tmp_path):
    """`partial` means some of it is in the product, and that half has to hold."""
    failing = json.dumps([sys.executable, "-c", "raise SystemExit(1)"])
    report = _resolved(tmp_path, f"""
        version: 1
        roadmap: test
        items:
          - id: P
            title: half in
            state: partial
            owner: me
            ungated_because: nothing gates it
            acceptance: [{{run: {failing}}}]
    """, run_commands=True)
    assert "acceptance fails" in _by_id(report)["P"].contradiction


# ---- the work queue -----------------------------------------------------


def test_actionable_is_ordered_by_register_score_with_unscored_last(tmp_path):
    """An unscored item was never weighed, so it does not lead the queue."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: LOW, title: low, state: planned, owner: me, score: 1.0, ungated_because: nothing gates it}
          - {id: NONE, title: unscored, state: planned, owner: me, ungated_because: nothing gates it}
          - {id: HIGH, title: high, state: planned, owner: me, score: 4.8, ungated_because: nothing gates it}
    """)
    assert [r.item.id for r in report.actionable] == ["HIGH", "LOW", "NONE"]


def test_a_blocked_external_names_who_owns_it(tmp_path):
    report = _resolved(tmp_path, _MINIMAL.replace(
        "ungated_because: a fixture that waits on nothing",
        "gates: [{kind: external, id: EXT-A}]"))
    assert "somebody" in _by_id(report)["A"].gates[0].detail


# ---- the CLI ------------------------------------------------------------


def test_cli_blocks_while_the_freeze_is_in_force(capsys):
    assert main(["roadmap"]) == 10
    out = capsys.readouterr().out
    assert "FREEZE IN FORCE" in out
    assert ("ACTIONABLE NOW" in out) or ("NOTHING IS ACTIONABLE" in out)


def test_cli_next_shows_the_queue_without_the_blocked_list(capsys):
    main(["roadmap", "--next"])
    out = capsys.readouterr().out
    assert ("ACTIONABLE NOW" in out) or ("NOTHING IS ACTIONABLE" in out)
    assert "BLOCKED\n" not in out


def test_an_empty_queue_says_so_rather_than_printing_a_blank_heading(tmp_path, capsys):
    """The live case since W8 shipped: every remaining item waits on an external.

    An empty list under a confident heading reads as "nothing to do". The
    output has to distinguish *finished* from *entirely blocked*, because they
    call for opposite responses.
    """
    body = """
        version: 1
        roadmap: test
        externals:
          EXT-A: {title: x, owner: somebody, attained: false}
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: external, id: EXT-A}]}
    """
    path = _write(tmp_path, textwrap.dedent(body).lstrip())
    main(["roadmap", "--roadmap", str(path)])
    out = capsys.readouterr().out
    assert "NOTHING IS ACTIONABLE" in out
    assert "Every item waits on something" in out


def test_cli_item_reports_every_gate_and_why(capsys):
    assert main(["roadmap", "--item", "W1"]) == 10
    out = capsys.readouterr().out
    assert "external T1" in out
    assert "OP-Vily" in out


def test_cli_rejects_an_unknown_item(capsys):
    assert main(["roadmap", "--item", "NOPE"]) == 2
    assert "no item NOPE" in capsys.readouterr().err


def test_cli_json_carries_the_graph(capsys):
    main(["--json", "roadmap"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["freeze_in_force"] is True
    assert isinstance(payload["actionable"], list)
    assert payload["contradictions"] == []
    first = payload["items"][0]
    assert {"id", "state", "verdict", "actionable", "gates", "blockers"} <= set(first)


def test_cli_says_when_commands_were_not_run(capsys):
    main(["roadmap"])
    assert "command(s) were not run" in capsys.readouterr().out


def test_cli_reports_a_broken_roadmap_as_an_error_not_a_verdict(tmp_path, capsys):
    bad = tmp_path / "roadmap.yaml"
    bad.write_text("items: [{id: A}]\n", encoding="utf-8")
    assert main(["roadmap", "--roadmap", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


# ---- resolved against the live gate, not against a status column --------


def _store(*controls: str) -> AttestationStore:
    from neuraxis import Attestation
    from neuraxis.model import now_utc

    issued = now_utc()
    return AttestationStore(
        Attestation(
            control=c, result=True, issued_at=issued,
            issuer="test-harness", evidence_ref=f"test://{c}",
        )
        for c in controls
    )


def _with(tmp_path, body: str, store: AttestationStore, **kw):
    return load_roadmap(_write(tmp_path, textwrap.dedent(body).lstrip())).resolve(
        load_registry(), store, **kw
    )


def test_a_band_gate_opens_when_the_band_actually_opens(tmp_path):
    body = """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: band_attained, id: BAND-A}]}
    """
    assert _by_id(_with(tmp_path, body, AttestationStore()))["A"].verdict == BLOCKED
    ready = _by_id(_with(tmp_path, body, _store("GV-01", "GV-03")))["A"]
    assert ready.verdict == READY and ready.actionable


def test_a_band_attained_only_on_a_waiver_still_blocks_the_plan(tmp_path, monkeypatch):
    """A waiver expires, so a plan built on one is a plan with a clock on it.

    The band is genuinely open and work inside it is genuinely licensed - that
    is what the waiver is for. Scheduling the *next* item against it is a
    different question, and the honest answer is no.
    """
    from neuraxis.model import BandStatus
    from neuraxis.resolver import BandResolver

    real = BandResolver.status

    def conditional(self, band_id, **kw):
        status = real(self, band_id, **kw)
        if band_id != "BAND-A":
            return status
        return BandStatus(
            band="BAND-A", attained=True, missing_controls=(), blocked_by=(),
            reasons=("attained on waiver",), waived_controls=("GV-01",),
            waiver_ids=("WV-1",),
        )

    monkeypatch.setattr(BandResolver, "status", conditional)
    item = _by_id(_with(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: band_attained, id: BAND-A}]}
    """, _store("GV-01", "GV-03")))["A"]
    assert item.verdict == BLOCKED
    assert "WV-1" in item.gates[0].detail


def test_a_control_gate_reads_the_same_freshness_window_the_gate_does(tmp_path):
    body = """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: control_attested, id: GV-01}]}
    """
    assert _by_id(_with(tmp_path, body, AttestationStore()))["A"].verdict == BLOCKED
    assert _by_id(_with(tmp_path, body, _store("GV-01")))["A"].verdict == READY


def test_an_unknown_control_is_unknown_not_a_crash(tmp_path):
    item = _by_id(_with(tmp_path, """
        version: 1
        roadmap: test
        items:
          - {id: A, title: A, state: planned, owner: me, gates: [{kind: control_attested, id: GV-99}]}
    """, AttestationStore()))["A"]
    assert item.verdict == UNKNOWN
    assert "not a control" in item.gates[0].detail


# ---- the remaining refusals --------------------------------------------


def test_a_gate_with_no_kind_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: planned, owner: me, gates: [{id: X}]}]
        """))
    assert "blocks nothing" in str(exc.value)


def test_a_gate_with_no_target_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: planned, owner: me, gates: [{kind: item}]}]
        """))
    assert "must name what it waits on" in str(exc.value)


def test_a_command_gate_with_no_command_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: planned, owner: me, gates: [{kind: command}]}]
        """))
    assert "satisfied by nothing" in str(exc.value)


def test_a_duplicate_item_id_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - {id: A, title: one, state: planned, owner: me}
              - {id: A, title: two, state: planned, owner: me}
        """))
    assert "duplicate item id" in str(exc.value)


def test_a_non_numeric_score_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items: [{id: A, title: A, state: planned, owner: me, score: high, ungated_because: x}]
        """))
    assert "score" in str(exc.value)


def test_an_acceptance_command_given_as_a_string_is_refused(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            items:
              - id: A
                title: A
                state: shipped
                owner: me
                acceptance: [{run: "neuraxis validate"}]
        """))
    assert "argv" in str(exc.value)


def test_a_missing_roadmap_file_is_an_error(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(tmp_path / "absent.yaml")
    assert "could not read" in str(exc.value)


def test_a_roadmap_that_is_not_a_mapping_is_refused(tmp_path):
    path = tmp_path / "roadmap.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(RoadmapError):
        load_roadmap(path)


def test_invalid_yaml_is_an_error_not_a_traceback(tmp_path):
    path = tmp_path / "roadmap.yaml"
    path.write_text("roadmap: test\nitems: [{id: A\n", encoding="utf-8")
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(path)
    assert "not valid YAML" in str(exc.value)


def test_a_lifted_freeze_reports_as_lifted(tmp_path):
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        freeze: {id: F, in_force: false}
        items: [{id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}]
    """)
    assert report.freeze_in_force is False


def test_no_freeze_at_all_reports_nothing(tmp_path):
    assert _resolved(tmp_path, _MINIMAL).freeze_in_force is None


def test_in_force_must_be_a_boolean(tmp_path):
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: test
            freeze: {id: F, in_force: "yes", lifts_when: [{kind: item, id: A}]}
            items: [{id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}]
        """))
    assert "boolean" in str(exc.value)


def test_a_freeze_lift_condition_that_is_not_an_item_is_reported_not_ignored(tmp_path):
    """Silently skipping it would lift the freeze on a condition nobody read."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: test
        freeze:
          id: F
          in_force: true
          lifts_when: [{kind: external, id: EXT-A}]
        externals:
          EXT-A: {title: x, owner: somebody, attained: true}
        items: [{id: A, title: A, state: planned, owner: me, gates: [{kind: external, id: EXT-A}]}]
    """)
    assert report.freeze_in_force is True
    assert "cannot be read here" in report.freeze_reasons[0]


# ---- the second adversarial review of the watchers (v0.19.0) ------------


def test_an_ungated_item_is_unknown_not_ready(tmp_path):
    """`all()` over an empty tuple is True, so an item with no gates reported
    READY and sorted to the top of the work queue. A permission-shaped object
    with no content is permission."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: t
        items: [{id: A, title: A, state: planned, owner: me, score: 9.9}]
    """)
    item = _by_id(report)["A"]
    assert item.verdict == UNKNOWN
    assert not item.actionable
    assert "no gates and no `ungated_because`" in item.gates[0].detail
    assert report.actionable == ()


def test_an_ungated_item_that_says_why_is_ready(tmp_path):
    """The positive control: emptiness is allowed when it is deliberate."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: t
        items:
          - {id: A, title: A, state: planned, owner: me, ungated_because: nothing gates it}
    """)
    assert _by_id(report)["A"].actionable


@pytest.mark.parametrize("key", ["gatez", "blocked_by", "gate"])
def test_a_misspelled_gates_key_is_a_load_failure(tmp_path, key):
    """One transposed letter put a blocked item at the top of the queue."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, f"""
            version: 1
            roadmap: t
            externals: {{T1: {{title: x, owner: o, attained: false}}}}
            items:
              - id: A
                title: A
                state: planned
                owner: me
                {key}: [{{kind: external, id: T1}}]
        """))
    assert key in str(exc.value)


def test_an_item_gate_reads_the_computed_verdict_not_the_typed_state(tmp_path):
    """An upstream declared `shipped` while its own gates were unsatisfied used
    to satisfy a downstream gate, and UNKNOWN could not propagate through an
    item gate at all - both against this module's headline promise."""
    report = _resolved(tmp_path, """
        version: 1
        roadmap: t
        externals: {T1: {title: x, owner: o, attained: false}}
        items:
          - {id: A, title: A, state: shipped, owner: me, gates: [{kind: external, id: T1}]}
          - {id: B, title: B, state: planned, owner: me, score: 5.0, gates: [{kind: item, id: A}]}
    """)
    items = _by_id(report)
    assert items["A"].verdict == BLOCKED and items["A"].contradiction
    assert items["B"].verdict == BLOCKED, "a shipped-but-blocked upstream satisfied the gate"
    assert report.actionable == ()


def test_unknown_propagates_through_an_item_gate(tmp_path):
    report = _resolved(tmp_path, """
        version: 1
        roadmap: t
        items:
          - {id: U, title: U, state: shipped, owner: me, gates: [{kind: band_attained, id: BAND-Z}]}
          - {id: D, title: D, state: planned, owner: me, score: 7.0, gates: [{kind: item, id: U}]}
    """, with_gate=True)
    items = _by_id(report)
    assert items["U"].verdict == UNKNOWN
    assert items["D"].verdict == UNKNOWN, "UNKNOWN did not propagate"


def test_a_failing_acceptance_blocks_rather_than_only_annotating(tmp_path):
    """It used to set `contradiction` and leave the verdict READY, so an item
    whose own acceptance failed sat in the actionable queue with no blockers."""
    failing = json.dumps([sys.executable, "-c", "raise SystemExit(1)"])
    report = _resolved(tmp_path, f"""
        version: 1
        roadmap: t
        items:
          - id: P
            title: half in
            state: partial
            owner: me
            ungated_because: nothing gates it
            acceptance: [{{run: {failing}}}]
    """, run_commands=True)
    item = _by_id(report)["P"]
    assert item.verdict == BLOCKED and not item.actionable
    assert item.contradiction


def test_an_honestly_partial_item_is_not_a_contradiction(tmp_path):
    """A review proposed widening the contradiction check to `has_shipped`.

    Taken verbatim that makes every honestly-partial item a contradiction: for
    a `partial` item the gates describe what blocks the REMAINDER, not what
    licensed the part already shipped. W9 is exactly that shape. The two halves
    are checked separately instead - `shipped` against its gates, and anything
    shipped against its acceptance.
    """
    report = _resolved(tmp_path, """
        version: 1
        roadmap: t
        externals: {T1: {title: x, owner: o, attained: false}}
        items:
          - id: W
            title: half done
            state: partial
            owner: me
            shipped_in: [v1.0.0]
            gates: [{kind: external, id: T1}]
    """)
    item = _by_id(report)["W"]
    assert item.verdict == BLOCKED
    assert not item.contradiction


def test_an_acceptance_run_typo_is_a_load_failure(tmp_path):
    """`runs:` for `run:` was discarded in silence, leaving `proves:` in the
    file and nothing running."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: t
            items:
              - id: A
                title: A
                state: shipped
                owner: me
                ungated_because: x
                acceptance: [{kind: command, runs: ["false"], proves: The thing is proven.}]
        """))
    assert "runs" in str(exc.value)


def test_an_acceptance_run_that_is_a_mapping_is_refused(tmp_path):
    """A mapping is truthy and iterates its KEYS, so it became a different,
    passing command."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: t
            items:
              - id: A
                title: A
                state: shipped
                owner: me
                ungated_because: x
                acceptance: [{run: {echo: hi}}]
        """))
    assert "list" in str(exc.value)


def test_a_declared_external_verifier_must_actually_run(tmp_path):
    """`External.verify` was parsed, stored and never executed - sitting in the
    file directly under `attained` and reading, in a diff, like proof. One
    edited token opened three items including the kernel boundary."""
    body = """
        version: 1
        roadmap: t
        externals:
          T1: {title: x, owner: o, attained: true, verify: ["false"]}
        items: [{id: A, title: A, state: planned, owner: me, gates: [{kind: external, id: T1}]}]
    """
    unrun = _by_id(_resolved(tmp_path, body))["A"]
    assert unrun.verdict == UNKNOWN and "was not run" in unrun.gates[0].detail
    ran = _by_id(_resolved(tmp_path, body, run_commands=True))["A"]
    assert ran.verdict == BLOCKED and "its own verifier disagrees" in ran.gates[0].detail


def test_a_boolean_score_is_refused(tmp_path):
    """`score: true` became 1.0. The sibling loader had this guard; this one did not."""
    with pytest.raises(RoadmapError):
        load_roadmap(_write(tmp_path, """
            version: 1
            roadmap: t
            items: [{id: A, title: A, state: planned, owner: me, score: true, ungated_because: x}]
        """))


def test_a_newer_schema_version_blocks_an_older_tool(tmp_path):
    """The rule this module already applied to an unrecognised gate kind, not
    previously applied to its own version field."""
    with pytest.raises(RoadmapError) as exc:
        load_roadmap(_write(tmp_path, """
            version: 99
            roadmap: t
            items: [{id: A, title: A, state: planned, owner: me, ungated_because: x}]
        """))
    assert "99" in str(exc.value)


def test_a_missing_schema_version_is_refused(tmp_path):
    with pytest.raises(RoadmapError):
        load_roadmap(_write(tmp_path, """
            roadmap: t
            items: [{id: A, title: A, state: planned, owner: me, ungated_because: x}]
        """))
