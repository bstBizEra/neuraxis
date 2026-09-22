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


# ---------------------------------------------------------------------------
# The command line, which is how anybody actually runs this
#
# Everything above exercises run_drill() and verify() as functions. main() -
# the plumbing that reaches them - was untested, and it is a third of the file:
# reading the log, picking the last record, rewriting the file. The refusals
# are useless if the path to them is broken, and this is the script that
# produces GV-05's evidence.
# ---------------------------------------------------------------------------


def _log_lines(path):
    return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_the_cli_runs_a_drill_and_appends_it(runner, tmp_path, capsys):
    log = tmp_path / "drill-log.jsonl"
    assert runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-1"]) == 0

    records = [json.loads(l) for l in _log_lines(log)]
    assert len(records) == 1
    assert records[0]["drill_id"] == "D-1"
    assert records[0]["outcome"] == "restored"
    assert records[0]["verifier"] == "", "the CLI filled in a verifier"


def test_the_cli_says_out_loud_that_it_will_not_verify(runner, tmp_path, capsys):
    """The refusal has to reach the operator, not only the record.

    A runner that quietly emitted an unverifiable record would be read as a
    completed drill by whoever ran it.
    """
    runner.main(["--target", "target.md", "--drill-id", "D-2"])
    err = capsys.readouterr().err
    assert "will not" in err and "--verify" in err


def test_the_cli_verifies_as_another_principal(runner, tmp_path):
    log = tmp_path / "drill-log.jsonl"
    runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-3"])
    assert runner.main(["--verify", str(log), "--as", "operator-vily"]) == 0

    record = json.loads(_log_lines(log)[-1])
    assert record["verifier"] == "operator-vily"
    assert record["verified_at"]


def test_the_cli_refuses_the_performer_as_verifier(runner, tmp_path):
    log = tmp_path / "drill-log.jsonl"
    runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-4"])
    performer = json.loads(_log_lines(log)[-1])["performer"]

    with pytest.raises(SystemExit):
        runner.main(["--verify", str(log), "--as", performer])

    # And the record on disk is untouched: a refused verification must not
    # leave a half-written claim behind.
    assert json.loads(_log_lines(log)[-1])["verifier"] == ""


def test_verifying_rewrites_only_the_last_record(runner, tmp_path):
    """The check worth writing.

    `--verify` reads every line, replaces the last, and writes the whole file
    back. If that ever mangles the earlier lines it would corrupt evidence
    silently - the log would still parse, still attest, and no longer say what
    happened. So the earlier records are compared byte for byte.
    """
    log = tmp_path / "drill-log.jsonl"
    runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-5"])
    runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-6"])
    before = _log_lines(log)
    assert len(before) == 2

    runner.main(["--verify", str(log), "--as", "operator-vily"])
    after = _log_lines(log)

    assert len(after) == 2
    assert after[0] == before[0], "an earlier drill record was rewritten"
    assert json.loads(after[1])["drill_id"] == "D-6"
    assert json.loads(after[1])["verifier"] == "operator-vily"


def test_verifying_an_empty_log_is_refused(runner, tmp_path):
    """No records is not 'nothing to do' - it is a claim with no subject."""
    log = tmp_path / "drill-log.jsonl"
    log.write_text("\n\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        runner.main(["--verify", str(log), "--as", "operator-vily"])


def test_a_log_written_with_a_bom_still_verifies(runner, tmp_path):
    """PowerShell writes a BOM. Every other reader here uses utf-8-sig and this
    one must too, or the drill fails for an encoding reason wearing a
    governance one."""
    log = tmp_path / "drill-log.jsonl"
    runner.main(["--target", "target.md", "--append", str(log), "--drill-id", "D-7"])
    log.write_text("﻿" + log.read_text(encoding="utf-8"), encoding="utf-8")

    assert runner.main(["--verify", str(log), "--as", "operator-vily"]) == 0
    assert json.loads(_log_lines(log)[-1])["verifier"] == "operator-vily"
