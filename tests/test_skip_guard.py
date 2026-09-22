"""A skipped test in CI is a test that did not run.

93 of this suite's 952 tests sit behind `pytest.skip("git is not available")`
— the drill runner's refusals, the ratification-gap check, and the whole
assist classifier. On a developer machine that guard is correct. In CI it was
a hole: git missing or broken on a runner would have removed a tenth of the
suite and the run would still have reported green.

The guard lives in tests/conftest.py. These tests hold it to the same contract
as everything else here, and the one that matters is
`test_the_hook_is_wired_not_merely_written` — the pure function can be perfect
while the hook is never called, which is the exact shape of the defect the
guard exists to catch.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from conftest import skip_verdict  # noqa: E402 - pytest puts tests/ on sys.path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = Path(__file__).resolve().parent / "conftest.py"


# --- the decision -----------------------------------------------------------


def test_a_skip_in_ci_fails():
    message = skip_verdict(in_ci=True, skipped=[("tests/test_x.py::test_y", "git is not available")])
    assert message is not None
    assert "test_x.py::test_y" in message
    assert "git is not available" in message


def test_a_skip_outside_ci_is_allowed():
    """Positive control. A developer without git still gets a usable suite,
    and a rule that made local work painful would be deleted within a week."""
    assert skip_verdict(in_ci=False, skipped=[("t::a", "git is not available")]) is None


def test_no_skips_in_ci_passes():
    """Vacuity probe. A guard that failed every CI run would be switched off."""
    assert skip_verdict(in_ci=True, skipped=[]) is None


def test_the_message_names_every_skip_up_to_a_limit():
    """A refusal listing 400 nodeids is a refusal nobody reads."""
    many = [(f"t::test_{n}", "reason") for n in range(50)]
    message = skip_verdict(in_ci=True, skipped=many)
    assert "and 30 more" in message
    assert message.count("t::test_") == 20


def test_a_skip_with_no_reason_still_reports():
    """An unexplained skip is the worst kind, so it must not print blank."""
    message = skip_verdict(in_ci=True, skipped=[("t::a", "")])
    assert "<no reason given>" in message


# --- the wiring -------------------------------------------------------------


def _run_pytest(tmp_path: Path, body: str, *, ci: bool) -> subprocess.CompletedProcess:
    """Run a throwaway suite under a copy of this repository's conftest."""
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(body, encoding="utf-8")

    env = dict(os.environ)
    env.pop("CI", None)
    if ci:
        env["CI"] = "true"
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=180,
    )


SKIPPING_SUITE = (
    "import pytest\n"
    "def test_passes():\n"
    "    assert True\n"
    "def test_skips():\n"
    "    pytest.skip('git is not available')\n"
)


def test_the_hook_is_wired_not_merely_written(tmp_path):
    """The check that matters: does the hook actually fire?

    `skip_verdict` could be flawless and never called. A guard that is written
    but not wired reports green exactly as loudly as one that works — which is
    the defect this whole file is about, one level up.
    """
    done = _run_pytest(tmp_path, SKIPPING_SUITE, ci=True)
    assert done.returncode != 0, f"a skip under CI did not fail the run:\n{done.stdout}"
    assert "did not run" in done.stdout
    assert "git is not available" in done.stdout


def test_the_same_suite_passes_outside_ci(tmp_path):
    """Positive control on the wiring, not only on the decision.

    Without this, a hook that failed every run would pass the test above and
    look correct doing it.
    """
    done = _run_pytest(tmp_path, SKIPPING_SUITE, ci=False)
    assert done.returncode == 0, f"a skip outside CI failed the run:\n{done.stdout}"


def test_a_clean_suite_passes_under_ci(tmp_path):
    done = _run_pytest(tmp_path, "def test_passes():\n    assert True\n", ci=True)
    assert done.returncode == 0, done.stdout


# --- the thing being protected ----------------------------------------------


def test_this_repository_skips_nothing_so_far_in_this_run():
    """If this fails, a skip was introduced and CI is about to go red.

    It reads the guard's own accumulator rather than a final tally, because it
    runs before the session ends. That makes it partial by construction — it
    sees only the tests that ran before it — so it is an early warning, not the
    control. The control is the sessionfinish hook.
    """
    import conftest

    assert conftest._SKIPPED == [], (
        "tests skipped in this run: "
        + "; ".join(nodeid for nodeid, _ in conftest._SKIPPED)
    )
