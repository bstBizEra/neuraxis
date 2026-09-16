"""The decision register as versioned config (W8, v0.16.0).

W8's ask is that a reversal trigger firing be **detectable rather than
remembered**. These tests are mostly about the two ways that fails: a ruling
whose enforcement point no longer exists, and a trigger nobody and nothing is
watching.
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from neuraxis import load_register, load_registry
from neuraxis.cli import main
from neuraxis.register import ARMED, CLEAR, UNRUN, WATCHED, RegisterError

_MINIMAL = """
    register: test
    rulings:
      D-01:
        title: A ruling
        ruling: Do the thing
        enforcement:
          - symbol: neuraxis.waiver:NON_COMPENSABLE_FLOOR
        reversal:
          trigger: The thing turns out badly
          owner: somebody
          review: quarterly
"""


def _write(tmp_path, body: str):
    path = tmp_path / "register.yaml"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


def _by_id(report):
    return {r.ruling.id: r for r in report.rulings}


# ---- the shipped register ----------------------------------------------


def test_the_shipped_register_loads():
    """Which, given the first invariant, also proves every named enforcement
    point still exists in the codebase."""
    register = load_register()
    assert set(register.rulings) == {f"D-0{n}" for n in range(1, 8)}


def test_d_07_is_folded_in_rather_than_left_as_an_addendum():
    register = load_register()
    assert register.revision == "B"
    assert register.rulings["D-07"].folded_from


def test_every_capability_a_ruling_depends_on_is_in_the_registry():
    """D-01 is enforced partly by IL-13a and IL-13b existing at all.

    Delete one from the registry and the ruling is unenforced, with nothing
    else in the suite noticing.
    """
    report = load_register().resolve(capabilities=tuple(load_registry().capabilities))
    unenforced = [r.ruling.id for r in report.rulings if not r.enforced]
    assert not unenforced, {r.ruling.id: r.missing for r in report.rulings if r.missing}


def test_no_trigger_is_armed_right_now():
    report = load_register().resolve(run_detectors=True)
    assert not report.armed, [(r.ruling.id, r.trigger.detail) for r in report.armed]


def test_the_triggers_no_machine_can_see_are_the_ones_we_expect():
    """Pinned deliberately. Moving a ruling from detected to watched is a real
    loss of coverage, and should not happen quietly."""
    report = load_register().resolve(run_detectors=True)
    assert {r.ruling.id for r in report.watched} == {"D-02", "D-03", "D-04", "D-07"}


def test_every_ruling_records_how_it_could_be_wrong():
    for ruling in load_register().rulings.values():
        assert ruling.reversal and ruling.reversal.trigger
        assert ruling.reversal.fallback, f"{ruling.id} names no fallback"


# ---- the first invariant: a ruling stays attached to its code -----------


def test_a_ruling_naming_a_symbol_that_does_not_exist_fails_to_load(tmp_path):
    """The whole point.

    A document can describe an enforcement point deleted three releases ago and
    read exactly as convincingly as one that exists.
    """
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "neuraxis.waiver:NON_COMPENSABLE_FLOOR", "neuraxis.waiver:RENAMED_AWAY")))
    assert "does not exist" in str(exc.value)
    assert "unattached" in str(exc.value)


def test_a_ruling_naming_a_missing_module_fails_to_load(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "neuraxis.waiver:NON_COMPENSABLE_FLOOR", "neuraxis.nosuch:thing")))
    assert "no module" in str(exc.value)


def test_a_dotted_symbol_resolves_through_the_class(tmp_path):
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "neuraxis.waiver:NON_COMPENSABLE_FLOOR",
        "neuraxis.gate:GovernanceGate._check_envelope")))
    assert register.rulings["D-01"].enforcement[0].symbol.endswith("_check_envelope")


def test_a_reference_with_no_colon_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "neuraxis.waiver:NON_COMPENSABLE_FLOOR", "neuraxis.waiver.SOMETHING")))
    assert "not a symbol reference" in str(exc.value)


def test_a_ruling_with_no_enforcement_point_is_refused(tmp_path):
    body = _MINIMAL.replace(
        "        enforcement:\n          - symbol: neuraxis.waiver:NON_COMPENSABLE_FLOOR\n", "")
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, body))
    assert "opinion that loses to schedule pressure" in str(exc.value)


def test_an_enforcement_entry_names_exactly_one_thing(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          - symbol: neuraxis.waiver:NON_COMPENSABLE_FLOOR",
            "          - {symbol: neuraxis.waiver:NON_COMPENSABLE_FLOOR, capability: IL-01}")))
    assert "exactly one" in str(exc.value)


# ---- the second invariant: detectable, or owned -------------------------


def test_a_trigger_that_is_neither_detectable_nor_owned_is_refused(tmp_path):
    """The invariant W8 exists for."""
    body = _MINIMAL.replace("          owner: somebody\n          review: quarterly\n", "")
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, body))
    assert "remembered" in str(exc.value)


def test_an_owner_without_a_cadence_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace("          review: quarterly\n", "")))
    assert "review cadence" in str(exc.value)


def test_a_ruling_with_no_reversal_condition_is_dogma(tmp_path):
    body = _MINIMAL.split("        reversal:")[0]
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, body))
    assert "dogma" in str(exc.value)


def test_a_trigger_with_no_text_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          trigger: The thing turns out badly", "          trigger: '  '")))
    assert "dogma" in str(exc.value)


def test_a_command_detector_must_say_which_exit_means_armed(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            "          detector: {kind: command, run: [echo, hi]}\n")))
    assert "which exit code means ARMED" in str(exc.value)


def test_armed_on_exit_zero_is_refused(tmp_path):
    """It would read every successful run as a fired trigger."""
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            "          detector: {kind: command, run: [echo, hi], armed_on_exit: 0}\n")))
    assert "every successful run" in str(exc.value)


def test_a_by_construction_detector_must_say_why(tmp_path):
    """Otherwise it is indistinguishable from a trigger nobody wired."""
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            "          detector: {kind: by_construction}\n")))
    assert "cannot fire" in str(exc.value)


def test_an_unknown_detector_kind_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            "          detector: {kind: vibes}\n")))
    assert "vibes" in str(exc.value)


def test_a_detector_command_given_as_a_string_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            '          detector: {kind: command, run: "neuraxis waivers", armed_on_exit: 10}\n')))
    assert "argv" in str(exc.value)


def test_a_duplicate_key_is_refused(tmp_path):
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL + """
      D-01:
        title: again
        ruling: again
"""))
    assert "duplicate key" in str(exc.value)


# ---- what the detectors report -----------------------------------------


def _detector(tmp_path, code: int, armed: int = 10):
    run = json.dumps([sys.executable, "-c", f"raise SystemExit({code})"])
    return load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        f"          detector: {{kind: command, run: {run}, armed_on_exit: {armed}}}\n")))


def test_a_detector_is_not_run_unless_asked(tmp_path):
    assert _by_id(_detector(tmp_path, 0).resolve())["D-01"].trigger.state == UNRUN


def test_not_run_is_not_clear(tmp_path):
    """The distinction the output makes out loud."""
    state = _by_id(_detector(tmp_path, 10).resolve())["D-01"].trigger
    assert state.state == UNRUN
    assert "nobody looked" in state.detail


def test_exit_zero_is_clear_and_the_armed_code_is_armed(tmp_path):
    assert _by_id(_detector(tmp_path, 0).resolve(run_detectors=True))["D-01"].trigger.state == CLEAR
    armed = _by_id(_detector(tmp_path, 10).resolve(run_detectors=True))["D-01"]
    assert armed.trigger.state == ARMED
    assert armed.trigger.armed


def test_a_third_exit_code_is_armed_not_clear(tmp_path):
    """A detector that cannot answer has not answered.

    Reading an unrecognised exit as clear is the caller-contract failure in a
    new place: the detector faulted, and the trigger it watches is now
    unwatched.
    """
    state = _by_id(_detector(tmp_path, 3).resolve(run_detectors=True))["D-01"].trigger
    assert state.state == ARMED
    assert "neither 0 nor the armed code" in state.detail


def test_a_missing_detector_binary_is_armed(tmp_path):
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: ["no-such-detector-xyz"], armed_on_exit: 10}\n')))
    state = _by_id(register.resolve(run_detectors=True))["D-01"].trigger
    assert state.state == ARMED
    assert "the detector is gone" in state.detail


def test_a_hanging_detector_is_armed(tmp_path):
    run = json.dumps([sys.executable, "-c", "import time; time.sleep(30)"])
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        f"          detector: {{kind: command, run: {run}, armed_on_exit: 10}}\n")))
    state = _by_id(register.resolve(run_detectors=True, timeout=1.0))["D-01"].trigger
    assert state.state == ARMED
    assert "timed out" in state.detail


def test_a_watched_trigger_names_its_owner(tmp_path):
    state = _by_id(load_register(_write(tmp_path, _MINIMAL)).resolve())["D-01"].trigger
    assert state.state == WATCHED
    assert "somebody" in state.detail and "quarterly" in state.detail


# ---- the CLI ------------------------------------------------------------


def test_cli_lists_every_ruling_and_its_enforcement(capsys):
    assert main(["register"]) == 0
    out = capsys.readouterr().out
    assert "ILR-001-DR Rev B" in out
    assert "neuraxis.waiver:NON_COMPENSABLE_FLOOR" in out
    assert "WATCHED BY A PERSON, NOT A MACHINE" in out


def test_cli_says_when_detectors_were_not_run(capsys):
    main(["register"])
    assert "NOT RUN is not CLEAR" in capsys.readouterr().out


def test_cli_ruling_reports_the_divergence(capsys):
    """D-01's trigger diverges from the register's wording, on purpose.

    A divergence recorded only in a companion doc is one a reader of the
    register will not see.
    """
    assert main(["register", "--ruling", "D-01"]) == 0
    out = capsys.readouterr().out
    assert "DIVERGENCE" in out
    assert "overridden by waiver" in out


def test_cli_rejects_an_unknown_ruling(capsys):
    assert main(["register", "--ruling", "D-99"]) == 2
    assert "no ruling D-99" in capsys.readouterr().err


def test_cli_blocks_when_a_trigger_is_armed(tmp_path, capsys):
    run = json.dumps([sys.executable, "-c", "raise SystemExit(10)"])
    path = _write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        f"          detector: {{kind: command, run: {run}, armed_on_exit: 10}}\n"))
    assert main(["register", "--register", str(path), "--check"]) == 10
    assert "TRIGGERS ARMED" in capsys.readouterr().out


def test_cli_json_carries_the_rulings(capsys):
    main(["--json", "register"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["revision"] == "B"
    assert payload["armed"] == []
    assert set(payload["watched"]) == {"D-02", "D-03", "D-04", "D-07"}
    first = payload["rulings"][0]
    assert {"id", "ruling", "enforcement", "enforced", "trigger"} <= set(first)


def test_cli_reports_a_broken_register_as_an_error(tmp_path, capsys):
    bad = tmp_path / "register.yaml"
    bad.write_text("rulings: []\n", encoding="utf-8")
    assert main(["register", "--register", str(bad)]) == 2
    assert "error:" in capsys.readouterr().err


# ---- the detector resolves the tool rather than assuming a PATH entry ---


def test_a_detector_calling_neuraxis_works_without_a_path_entry(tmp_path, monkeypatch):
    """A PATH miss is not evidence about the register.

    Spelling the detector's command as the literal string `neuraxis` would make
    it depend on an install location, and report a trigger armed because the
    tool lives somewhere else. That is also the substitutability problem D-07's
    own contract identifies, occurring in the thing that watches D-07.
    """
    import neuraxis.register as mod

    monkeypatch.delenv("NEURAXIS_BIN", raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: [neuraxis, validate], armed_on_exit: 10}\n')))
    assert _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state == CLEAR


def test_the_detector_honours_the_same_env_vars_the_caller_contract_uses(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURAXIS_BIN", sys.executable)
    monkeypatch.setenv("NEURAXIS_BIN_ARGS", json.dumps(["-c", "raise SystemExit(10)"]))
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: [neuraxis, validate], armed_on_exit: 10}\n')))
    assert _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state == ARMED


def test_a_malformed_bin_args_arms_rather_than_silently_using_another_binary(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("NEURAXIS_BIN", sys.executable)
    monkeypatch.setenv("NEURAXIS_BIN_ARGS", "not json")
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: [neuraxis, validate], armed_on_exit: 10}\n')))
    state = _by_id(register.resolve(run_detectors=True))["D-01"].trigger
    assert state.state == ARMED
    assert "could not be resolved" in state.detail


def test_a_detector_that_is_not_neuraxis_is_left_alone(tmp_path):
    run = json.dumps([sys.executable, "-c", "raise SystemExit(0)"])
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        f"          detector: {{kind: command, run: {run}, armed_on_exit: 10}}\n")))
    assert _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state == CLEAR
