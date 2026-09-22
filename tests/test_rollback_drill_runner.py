"""The GV-05 drill runner (scripts/rollback_drill.py).

The runner's job is to produce evidence, and the only interesting thing about
it is what it refuses to produce. It performs the drill, so it cannot also be
the principal that verifies it — and a runner with a `--verifier` flag would
make writing a true-looking, false record a one-liner.

So these tests are mostly about the refusals, plus one end-to-end pass that
proves the honest path actually reaches an attestation: drill, verify as
somebody else, and the provider attests GV-05.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from neuraxis.providers import run_provider
from neuraxis.providers.drill import RollbackDrillProvider

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollback_drill.py"


def _load():
    spec = importlib.util.spec_from_file_location("rollback_drill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """The runner pointed at a throwaway git repo, not this one."""
    def git(*args: str) -> int:
        try:
            return subprocess.run(
                ["git", "-C", str(tmp_path), *args], capture_output=True, check=False
            ).returncode
        except (OSError, subprocess.SubprocessError):
            pytest.skip("git is not available")
            return 1

    if git("init", "--quiet") != 0:
        pytest.skip("git init failed in this environment")
    git("config", "user.email", "suite@example.invalid")
    git("config", "user.name", "suite")
    (tmp_path / "target.md").write_text("baseline content\n", encoding="utf-8")
    git("add", "-A")
    if git("commit", "--quiet", "-m", "fixture") != 0:
        pytest.skip("git commit failed in this environment")

    module = _load()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def _drill(runner, tmp_path):
    return runner.run_drill(tmp_path / "target.md", "DRILL-TEST")


# ---------------------------------------------------------------------------
# What it produces
# ---------------------------------------------------------------------------


def test_a_drill_really_mutates_and_really_restores(runner, tmp_path):
    record = _drill(runner, tmp_path)
    assert record["outcome"] == "restored"
    assert record["baseline_digest"] == record["restored_digest"]
    # The mutation was real: a drill whose "mutation" changed nothing would be
    # the vacuous drill the provider's fourth breach is about.
    assert record["mutated_digest"] != record["baseline_digest"]
    assert record["mutated"] == ["target.md"]
    # And the file is genuinely back.
    assert (tmp_path / "target.md").read_text(encoding="utf-8") == "baseline content\n"


def test_the_runner_leaves_the_verifier_empty(runner, tmp_path):
    """The whole point. It performed the drill; it is not the verifier."""
    record = _drill(runner, tmp_path)
    assert record["verifier"] == ""
    assert record["verified_at"] == ""


def test_an_unverified_drill_does_not_attest(runner, tmp_path, monkeypatch):
    """A real, honest, successful drill still refuses to attest the control."""
    log = tmp_path / "drill-log.jsonl"
    log.write_text(json.dumps(_drill(runner, tmp_path)) + "\n", encoding="utf-8")
    result = run_provider(RollbackDrillProvider(drill_log_path=log))
    assert not result.attests
    assert "no verifier recorded" in result.result.detail


def test_a_dirty_target_is_refused(runner, tmp_path):
    """A drill against uncommitted changes cannot tell restored from unsaved."""
    (tmp_path / "target.md").write_text("uncommitted edit\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="uncommitted changes"):
        _drill(runner, tmp_path)


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


def test_the_performer_may_not_verify_its_own_drill(runner, tmp_path):
    record = _drill(runner, tmp_path)
    with pytest.raises(SystemExit, match="NX-INV-2"):
        runner.verify(record, record["performer"])


def test_an_unnamed_principal_is_refused(runner, tmp_path):
    record = _drill(runner, tmp_path)
    with pytest.raises(SystemExit, match="must name the principal"):
        runner.verify(record, "   ")


def test_verification_recomputes_rather_than_trusting_the_record(runner, tmp_path):
    """If the file has moved since the drill, the record cannot be verified."""
    record = _drill(runner, tmp_path)
    (tmp_path / "target.md").write_text("changed after the drill\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not at the recorded baseline"):
        runner.verify(record, "some-human")


def test_the_runner_exposes_no_way_to_set_the_verifier_at_drill_time():
    """A `--verifier` flag would make a true-looking false record a one-liner."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--verifier" not in source
    assert '"verifier": ""' in source or '"verifier": "",' in source


# ---------------------------------------------------------------------------
# The honest path, end to end
# ---------------------------------------------------------------------------


def test_a_drill_verified_by_another_principal_attests_gv_05(runner, tmp_path):
    """Drill, verify as somebody who did not perform it, and the control holds."""
    record = runner.verify(_drill(runner, tmp_path), "ounkhamvilay")
    assert record["verifier"] == "ounkhamvilay"
    assert record["verified_at"]

    log = tmp_path / "drill-log.jsonl"
    log.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = run_provider(RollbackDrillProvider(drill_log_path=log))
    assert result.attests, result.result.detail
    assert result.to_attestation().result is True
