"""The per-file coverage floor (scripts/coverage_floor.py).

`fail_under = 90` passed for weeks while scripts/rollback_drill.py sat at 61%
with its whole main() untested. The total really was 93%; the average simply
cannot see one file being abandoned.

So the test that matters here is `test_it_catches_the_defect_it_was_built_for`,
which replays those exact numbers. A floor that would not have caught the
failure that motivated it is decoration, and this is the only way to know.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "coverage_floor.py"
NOW = "2026-09-22T12:00:00+00:00"


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("coverage_floor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def write_report(path: Path, files: dict[str, float], *, timestamp: str | None = NOW) -> Path:
    report = {
        "files": {
            name: {"summary": {"percent_covered": pct, "num_statements": 50}}
            for name, pct in files.items()
        }
    }
    if timestamp is not None:
        report["meta"] = {"timestamp": timestamp}
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def run(module, *args: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = module.main(["--now", NOW, *args])
    return code, buffer.getvalue()


# --- the defect it exists for -----------------------------------------------


def test_it_catches_the_defect_it_was_built_for(module, tmp_path):
    """The real numbers from 2026-09-22, before #24.

    Aggregate 93%, and one file at 61% that nothing was watching. If this ever
    passes, the floor has stopped doing the only job it was added for.
    """
    report = write_report(
        tmp_path / "coverage.json",
        {
            "scripts/rollback_drill.py": 61.11,
            "scripts/ratification_gap.py": 90.98,
            "src/neuraxis/gate.py": 99.0,
        },
    )
    code, out = run(module, "--report", str(report), "--floor", "85")
    assert code == module.EXIT_BELOW
    assert "rollback_drill.py" in out
    assert "61.11" in out
    assert "ratification_gap.py" not in out, "a file above the floor was reported"


# --- ordinary operation -----------------------------------------------------


def test_all_above_the_floor_passes(module, tmp_path):
    """Positive control. A floor that flagged every run would be lowered to
    nothing within a week."""
    report = write_report(tmp_path / "coverage.json", {"a.py": 89.8, "b.py": 99.0})
    code, out = run(module, "--report", str(report), "--floor", "85")
    assert code == module.EXIT_OK
    assert "all 2 file(s)" in out
    assert "worst 89.80%" in out


def test_the_worst_offender_is_listed_first(module, tmp_path):
    """A list nobody can triage is a list nobody reads."""
    report = write_report(
        tmp_path / "coverage.json", {"bad.py": 10.0, "worse.py": 5.0, "ok.py": 99.0}
    )
    _, out = run(module, "--report", str(report), "--floor", "85")
    assert out.index("worse.py") < out.index("bad.py")


def test_a_file_exactly_on_the_floor_passes(module, tmp_path):
    """`<` not `<=`: a floor is a minimum you may sit on, and off-by-one here
    fires on a file that met the bar exactly."""
    report = write_report(tmp_path / "coverage.json", {"a.py": 85.0})
    assert run(module, "--report", str(report), "--floor", "85")[0] == module.EXIT_OK


# --- fail closed ------------------------------------------------------------


def test_a_report_covering_nothing_cannot_run(module, tmp_path):
    """The dangerous case: an empty report is not 'every file passes'.

    If the suite failed to run, or coverage measured nothing, the honest answer
    is that the floor was not checked - not that it held.
    """
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"files": {}, "meta": {"timestamp": NOW}}), encoding="utf-8")
    code, out = run(module, "--report", str(report), "--floor", "85")
    assert code == module.EXIT_CANNOT_RUN
    assert "covers no files" in out


def test_a_missing_report_cannot_run(module, tmp_path):
    code, out = run(module, "--report", str(tmp_path / "nope.json"))
    assert code == module.EXIT_CANNOT_RUN
    assert "no coverage report" in out


def test_malformed_json_cannot_run(module, tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text("{not json", encoding="utf-8")
    assert run(module, "--report", str(report))[0] == module.EXIT_CANNOT_RUN


def test_a_report_without_a_files_section_cannot_run(module, tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 99}}), encoding="utf-8")
    code, out = run(module, "--report", str(report))
    assert code == module.EXIT_CANNOT_RUN
    assert "no 'files' section" in out


def test_an_impossible_floor_cannot_run(module, tmp_path):
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0})
    assert run(module, "--report", str(report), "--floor", "0")[0] == module.EXIT_CANNOT_RUN
    assert run(module, "--report", str(report), "--floor", "101")[0] == module.EXIT_CANNOT_RUN


# --- staleness --------------------------------------------------------------


def test_a_stale_report_cannot_run(module, tmp_path):
    """Reading an old artefact reports old health in today's voice.

    That is exactly what the drift baseline did for three releases, so this
    check refuses rather than trusts.
    """
    old = (datetime.fromisoformat(NOW) - timedelta(hours=3)).isoformat()
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0}, timestamp=old)
    code, out = run(module, "--report", str(report), "--max-age-minutes", "60")
    assert code == module.EXIT_CANNOT_RUN
    assert "older run" in out


def test_a_fresh_report_is_accepted(module, tmp_path):
    recent = (datetime.fromisoformat(NOW) - timedelta(minutes=2)).isoformat()
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0}, timestamp=recent)
    assert run(module, "--report", str(report), "--max-age-minutes", "60")[0] == module.EXIT_OK


def test_a_report_with_no_timestamp_cannot_have_its_age_checked(module, tmp_path):
    """Absent is not fresh. The same rule the providers apply to evidence."""
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0}, timestamp=None)
    code, out = run(module, "--report", str(report), "--max-age-minutes", "60")
    assert code == module.EXIT_CANNOT_RUN
    assert "meta.timestamp" in out


def test_the_staleness_check_can_be_switched_off_explicitly(module, tmp_path):
    """0 disables it. An operator reading an old report on purpose is fine;
    doing it by accident is what the default prevents."""
    old = (datetime.fromisoformat(NOW) - timedelta(days=9)).isoformat()
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0}, timestamp=old)
    assert run(module, "--report", str(report), "--max-age-minutes", "0")[0] == module.EXIT_OK


def test_coverage_pys_own_naive_timestamp_is_handled(module, tmp_path):
    """coverage.py writes local time with no offset. Guessing UTC would make a
    report look hours old, or hours in the future, depending on the runner."""
    naive = datetime.now().replace(microsecond=0).isoformat()
    report = write_report(tmp_path / "coverage.json", {"a.py": 99.0}, timestamp=naive)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = module.main(["--report", str(report), "--max-age-minutes", "60"])
    assert code == module.EXIT_OK, buffer.getvalue()

