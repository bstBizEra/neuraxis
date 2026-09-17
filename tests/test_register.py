"""The decision register as versioned config (W8, v0.16.0).

W8's ask is that a reversal trigger firing be **detectable rather than
remembered**. These tests are mostly about the two ways that fails: a ruling
whose enforcement point no longer exists, and a trigger nobody and nothing is
watching.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

import pytest

from neuraxis import load_register, load_registry
from neuraxis.cli import main
from neuraxis.register import ARMED, CLEAR, SEALED, UNRUN, WATCHED, RegisterError

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


# ---- the detector runs THIS package, not something from the environment --


def test_the_environment_cannot_turn_a_detector_clear(tmp_path, monkeypatch):
    """The v0.16.0 fix introduced a worse hole than the one it closed.

    It resolved `NEURAXIS_BIN` first so a PATH miss would not report a trigger
    armed. That reasoning is right for avoiding a false ARM and was applied to
    a mechanism that manufactures a false CLEAR: `NEURAXIS_BIN=/bin/true` - or
    a two-line `exit 0` script named `neuraxis` earlier on PATH - turned every
    detector CLEAR. In a fail-closed system a false CLEAR is strictly worse.
    """
    shim = tmp_path / "bin"
    shim.mkdir()
    fake = shim / "neuraxis"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)

    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: [neuraxis, waivers], armed_on_exit: 10}\n')))

    honest = _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state

    monkeypatch.setenv("NEURAXIS_BIN", "/bin/true")
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    rigged = _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state

    assert rigged == honest, "the environment changed the detector's answer"


def test_a_detector_naming_neuraxis_runs_this_interpreter(tmp_path, monkeypatch):
    """No PATH entry required: a PATH miss is not evidence about the register."""
    monkeypatch.delenv("NEURAXIS_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        '          detector: {kind: command, run: [neuraxis, validate], armed_on_exit: 10}\n')))
    assert _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state == CLEAR


def test_a_detector_that_is_not_neuraxis_is_left_alone(tmp_path):
    run = json.dumps([sys.executable, "-c", "raise SystemExit(0)"])
    register = load_register(_write(tmp_path, _MINIMAL.replace(
        "          owner: somebody\n          review: quarterly\n",
        f"          detector: {{kind: command, run: {run}, armed_on_exit: 10}}\n")))
    assert _by_id(register.resolve(run_detectors=True))["D-01"].trigger.state == CLEAR


# ---- enforced, sealed, and not-run are all distinct from clear ----------


def test_the_default_call_does_not_report_everything_enforced():
    """`and known` short-circuited on an empty set, so the DEFAULT call - which
    is what a caller whose registry failed to load passes - reported every
    ruling enforced. Supplying NOTHING read as everything present while
    supplying the WRONG list read as missing: exactly backwards."""
    report = load_register().resolve()
    capability_rulings = [r for r in report.rulings if r.missing or r.unchecked]
    assert capability_rulings, "no ruling depends on a capability; this test is vacuous"
    for r in capability_rulings:
        assert r.unchecked and not r.enforced


def test_supplying_the_registry_reports_them_enforced():
    from neuraxis import load_registry

    report = load_register().resolve(capabilities=tuple(load_registry().capabilities))
    assert all(r.enforced and not r.unchecked for r in report.rulings)


def test_a_sealed_trigger_is_not_reported_clear_and_is_never_invisible():
    """`by_construction` returned CLEAR and appeared in neither the armed nor
    the watched list, so deleting `owner`/`review` and writing
    `detector: {kind: by_construction, why: "."}` was the cheapest way to make
    an inconvenient trigger disappear from every list in the report."""
    report = load_register().resolve(run_detectors=True)
    sealed = report.sealed
    assert sealed, "nothing is sealed; this test is vacuous"
    for r in sealed:
        assert r.trigger.state == SEALED
        assert r.ruling.reversal.owner and r.ruling.reversal.review


def test_a_thin_reason_for_sealing_is_refused(tmp_path):
    for why in ('"."', '"TODO"', '"obvious"'):
        with pytest.raises(RegisterError) as exc:
            load_register(_write(tmp_path, _MINIMAL.replace(
                "          owner: somebody\n          review: quarterly\n",
                f"          detector: {{kind: by_construction, why: {why}}}\n")))
        assert "in a sentence" in str(exc.value)


def test_sealing_still_needs_an_owner(tmp_path):
    long_why = "The block derives from the matrix and no separate clause exists to drift."
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "          owner: somebody\n          review: quarterly\n",
            f'          detector: {{kind: by_construction, why: "{long_why}"}}\n')))
    assert "somebody has to be the one who notices" in str(exc.value)


def test_not_run_appears_in_its_own_list():
    """It was in neither `armed` nor `watched`, and `UNRUN` was not exported,
    so a consumer reading `armed == []` as clear got green for detectors nobody
    ran and could not even name the state to filter on."""
    import neuraxis.register as mod

    assert "UNRUN" in mod.__all__ and "SEALED" in mod.__all__
    report = load_register().resolve()
    assert {r.ruling.id for r in report.unrun} == {"D-01", "D-05"}
    assert report.to_dict()["not_run"]


def test_a_symbol_outside_this_package_is_refused(tmp_path):
    """`importlib.import_module` on a string from a config file RUNS it, and
    `neuraxis register` looks like a read-only status command."""
    with pytest.raises(RegisterError) as exc:
        load_register(_write(tmp_path, _MINIMAL.replace(
            "neuraxis.waiver:NON_COMPENSABLE_FLOOR", "os:system")))
    assert "inside this package" in str(exc.value)


def test_symbol_resolution_does_not_run_descriptors(tmp_path):
    """`hasattr` then `getattr` ran every descriptor twice, and a module-level
    `__getattr__` - the standard deprecation-shim pattern - satisfied any name
    at all, which would have made this whole check vacuous the day one landed."""
    import inspect

    import neuraxis.register as mod

    source = inspect.getsource(mod._resolve)
    assert "getattr_static" in source
    assert "hasattr(" not in source
