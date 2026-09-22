"""CLI surface for providers and assure (v0.3)."""

from __future__ import annotations

import json

import pytest

from neuraxis.cli import main


def _run(argv, capsys):
    code = main(argv)
    return code, capsys.readouterr()


@pytest.fixture
def clean_log(tmp_path):
    path = tmp_path / "task-log.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"task_id": "t1", "performer": "agent-drafter", "verifier": "github-ci"},
                {"task_id": "t2", "performer": "agent-motor", "verifier": "github-ci"},
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def dirty_log(tmp_path):
    path = tmp_path / "dirty-log.jsonl"
    path.write_text(
        json.dumps({"task_id": "t3", "performer": "agent-cortex", "verifier": "agent-cortex"}),
        encoding="utf-8",
    )
    return path


# ---- providers ---------------------------------------------------------


def test_providers_lists_every_control(capsys, registry):
    code, out = _run(["--json", "providers"], capsys)
    payload = json.loads(out.out)
    assert code == 0
    assert set(payload["controls"]) == set(registry.controls)
    assert payload["total"] == 10


def test_providers_reports_wired_count_and_blockers(capsys):
    code, out = _run(["--json", "providers"], capsys)
    payload = json.loads(out.out)
    assert payload["wired"] == 5
    for control in ("GV-02", "GV-04", "GV-05", "GV-06", "GV-07"):
        assert payload["controls"][control]["state"] == "wired"
    assert payload["controls"]["GV-01"]["state"] == "unwired"
    assert "KBS-001" in payload["controls"]["GV-01"]["blocked_on"]


def test_providers_shows_each_controls_own_window(capsys):
    payload = json.loads(_run(["--json", "providers"], capsys)[1].out)
    assert payload["controls"]["GV-01"]["window"] == "1d"
    assert payload["controls"]["GV-05"]["window"] == "30d"


# ---- assure ------------------------------------------------------------


def test_assure_records_results_and_reports_unwired(tmp_path, clean_log, capsys):
    store = tmp_path / "a.jsonl"
    code, out = _run(
        ["--json", "--attestations", str(store), "--task-log", str(clean_log), "assure"], capsys
    )
    payload = json.loads(out.out)
    # Non-zero: GV-07 is wired but its gate log was not supplied, so it fails.
    # A wired control with an absent source is a control that does not hold —
    # treating it as a skip would be the vacuous pass the harness exists to stop.
    assert code == 10
    # Every wired control except GV-04 fails here: only --task-log was
    # supplied, so the others have no source. That is the correct outcome —
    # a check with no source is not a check that passed. Sorted because
    # provider ordering is not part of the contract.
    assert sorted(payload["failed"]) == ["GV-02", "GV-05", "GV-06", "GV-07"]
    assert len(payload["unwired"]) == 5
    assert store.is_file()


def test_assure_exits_nonzero_on_a_failing_provider(tmp_path, dirty_log, capsys):
    code, out = _run(
        [
            "--json", "--attestations", str(tmp_path / "a.jsonl"),
            "--task-log", str(dirty_log), "assure", "--control", "GV-04",
        ],
        capsys,
    )
    payload = json.loads(out.out)
    assert code == 10
    assert payload["failed"] == ["GV-04"]


def test_assure_skips_controls_that_are_still_current(tmp_path, clean_log, capsys):
    store = tmp_path / "a.jsonl"
    args = ["--json", "--attestations", str(store), "--task-log", str(clean_log),
            "assure", "--control", "GV-04"]
    _run(args, capsys)
    payload = json.loads(_run(args, capsys)[1].out)
    assert payload["ran"] == []
    assert payload["skipped_current"] == 1


def test_assure_force_reruns_a_current_control(tmp_path, clean_log, capsys):
    store = tmp_path / "a.jsonl"
    args = ["--json", "--attestations", str(store), "--task-log", str(clean_log),
            "assure", "--control", "GV-04"]
    _run(args, capsys)
    payload = json.loads(_run(args + ["--force"], capsys)[1].out)
    assert len(payload["ran"]) == 1


def test_assure_reports_a_band_closing(tmp_path, clean_log, dirty_log, capsys):
    """A band that closes is the signal the whole schedule exists to surface."""
    store = tmp_path / "a.jsonl"
    # Open BAND-A and BAND-B by hand, then let a failing provider close them.
    for control in ("GV-01", "GV-02", "GV-03", "GV-05"):
        _run(
            ["--attestations", str(store), "attest", "--control", control,
             "--result", "pass", "--issuer", "op", "--evidence-ref", "manual"],
            capsys,
        )
    _run(
        ["--attestations", str(store), "--task-log", str(clean_log),
         "assure", "--control", "GV-04"],
        capsys,
    )
    code, out = _run(
        ["--json", "--attestations", str(store), "--task-log", str(dirty_log),
         "assure", "--control", "GV-04", "--force"],
        capsys,
    )
    payload = json.loads(out.out)
    assert code == 10
    assert "BAND-B" in payload["bands_closed"]


def test_assure_rejects_an_unknown_control(tmp_path, capsys):
    code, _ = _run(
        ["--attestations", str(tmp_path / "a.jsonl"), "assure", "--control", "GV-99"], capsys
    )
    assert code == 2


# ---- attest --from-provider --------------------------------------------


def test_attest_from_provider_records_the_run(tmp_path, clean_log, capsys):
    store = tmp_path / "a.jsonl"
    code, out = _run(
        [
            "--json", "--attestations", str(store), "--task-log", str(clean_log),
            "attest", "--control", "GV-04", "--from-provider", "nx/verifier-independence",
        ],
        capsys,
    )
    payload = json.loads(out.out)
    assert code == 0
    assert payload["attests"] is True
    assert payload["control"] == "GV-04"


def test_attest_from_provider_exits_nonzero_when_the_check_fails(tmp_path, dirty_log, capsys):
    code, _ = _run(
        [
            "--attestations", str(tmp_path / "a.jsonl"), "--task-log", str(dirty_log),
            "attest", "--control", "GV-04", "--from-provider", "nx/verifier-independence",
        ],
        capsys,
    )
    assert code == 10


def test_attest_rejects_a_provider_for_a_different_control(tmp_path, clean_log, capsys):
    code, _ = _run(
        [
            "--attestations", str(tmp_path / "a.jsonl"), "--task-log", str(clean_log),
            "attest", "--control", "GV-01", "--from-provider", "nx/verifier-independence",
        ],
        capsys,
    )
    assert code == 2


def test_attest_rejects_an_unknown_provider(tmp_path, capsys):
    code, _ = _run(
        ["--attestations", str(tmp_path / "a.jsonl"), "attest",
         "--control", "GV-04", "--from-provider", "nx/nope"],
        capsys,
    )
    assert code == 2


def test_manual_attest_still_requires_its_three_arguments(tmp_path, capsys):
    code, _ = _run(
        ["--attestations", str(tmp_path / "a.jsonl"), "attest", "--control", "GV-04"], capsys
    )
    assert code == 2


def test_validate_reports_per_control_windows(capsys):
    payload = json.loads(_run(["--json", "validate"], capsys)[1].out)
    assert payload["windows"]["GV-01"] == 86400
    assert payload["windows"]["GV-05"] == 2592000
