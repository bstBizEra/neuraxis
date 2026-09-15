"""CLI contract — exit codes and JSON shape.

Non-Python callers depend on these. A change here is a breaking change to the
maw-js integration, so each code is pinned by a test.
"""

from __future__ import annotations

import io
import json

import pytest

from neuraxis.cli import main
from neuraxis.model import now_utc


@pytest.fixture
def attestation_file(tmp_path, registry):
    path = tmp_path / "attestations.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for control in registry.controls:
            handle.write(
                json.dumps(
                    {
                        "control": control, "result": True,
                        "issued_at": now_utc().isoformat(),
                        "issuer": "harness", "evidence_ref": f"test://{control}",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return path


def _run(argv, capsys):
    code = main(argv)
    return code, capsys.readouterr()


def test_validate_succeeds_on_bundled_registry(capsys):
    code, out = _run(["validate"], capsys)
    assert code == 0
    assert "bst-neuraxis" in out.out


def test_validate_json_shape(capsys):
    code, out = _run(["--json", "validate"], capsys)
    payload = json.loads(out.out)
    assert code == 0
    assert payload["valid"] is True
    assert payload["capabilities"] == 33


def test_status_with_no_attestations_reports_all_blocked(tmp_path, capsys):
    code, out = _run(
        ["--json", "--attestations", str(tmp_path / "none.jsonl"), "status"], capsys
    )
    payload = json.loads(out.out)
    assert code == 0
    assert payload["attained"] == []


def test_status_with_full_attestations_reports_all_attained(attestation_file, capsys):
    code, out = _run(["--json", "--attestations", str(attestation_file), "status"], capsys)
    payload = json.loads(out.out)
    assert code == 0
    assert len(payload["attained"]) == 7


def test_gate_allow_exits_zero(attestation_file, capsys):
    code, out = _run(
        [
            "--json", "--attestations", str(attestation_file), "gate",
            "--capability", "IL-06", "--identity", "agent-drafter", "--role", "drafter",
            "--intent", "run pipeline", "--verifier", "github-ci", "--rollback-tested",
        ],
        capsys,
    )
    assert code == 0
    assert json.loads(out.out)["decision"] == "ALLOW"


def test_gate_deny_exits_ten(tmp_path, capsys):
    code, _ = _run(
        [
            "--attestations", str(tmp_path / "none.jsonl"), "gate",
            "--capability", "IL-06", "--identity", "a", "--role", "drafter",
            "--intent", "x", "--verifier", "ci", "--rollback-tested",
        ],
        capsys,
    )
    assert code == 10


def test_gate_escalate_exits_eleven(attestation_file, capsys):
    code, _ = _run(
        [
            "--attestations", str(attestation_file), "gate",
            "--capability", "IL-06", "--identity", "a", "--role", "drafter",
            "--intent", "x", "--verifier", "ci", "--rollback-tested", "--risk", "CRITICAL",
        ],
        capsys,
    )
    assert code == 11


def test_gate_wait_for_authority_exits_twelve(attestation_file, capsys):
    code, _ = _run(
        [
            "--attestations", str(attestation_file), "gate",
            "--capability", "IL-31", "--identity", "op", "--role", "operator",
            "--intent", "x", "--verifier", "council", "--rollback-tested",
        ],
        capsys,
    )
    assert code == 12


def test_gate_delegate_exits_thirteen(attestation_file, capsys):
    code, _ = _run(
        [
            "--attestations", str(attestation_file), "gate",
            "--capability", "IL-17", "--identity", "d", "--role", "drafter",
            "--intent", "x", "--verifier", "ci", "--rollback-tested",
        ],
        capsys,
    )
    assert code == 13


def test_gate_reads_json_request_from_stdin(attestation_file, capsys, monkeypatch):
    request = {
        "intent": "run pipeline", "identity": "agent-drafter", "role": "drafter",
        "capability": "IL-06", "scope": "bst-sa", "verifier": "github-ci",
        "rollback_tested": True,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    code, out = _run(["--json", "--attestations", str(attestation_file), "gate", "-"], capsys)
    assert code == 0
    assert json.loads(out.out)["decision"] == "ALLOW"


def test_gate_rejects_malformed_stdin_with_error_code(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    code, _ = _run(["gate", "-"], capsys)
    assert code == 2


def test_missing_required_args_exit_two(capsys):
    code, _ = _run(["gate", "--capability", "IL-06"], capsys)
    assert code == 2


def test_attest_records_and_opens_a_band(tmp_path, capsys):
    path = tmp_path / "attestations.jsonl"
    for control in ("GV-01", "GV-03"):
        code, _ = _run(
            [
                "--attestations", str(path), "attest", "--control", control,
                "--result", "pass", "--issuer", "operator", "--evidence-ref", "ev://1",
            ],
            capsys,
        )
        assert code == 0

    code, out = _run(["--json", "--attestations", str(path), "status"], capsys)
    assert json.loads(out.out)["attained"] == ["BAND-A"]


def test_attest_rejects_unknown_control(tmp_path, capsys):
    code, _ = _run(
        [
            "--attestations", str(tmp_path / "a.jsonl"), "attest", "--control", "GV-99",
            "--result", "pass", "--issuer", "op", "--evidence-ref", "x",
        ],
        capsys,
    )
    assert code == 2


def test_score_blocks_when_performer_verifies_itself(attestation_file, capsys):
    code, out = _run(
        [
            "--json", "--attestations", str(attestation_file), "score", "--band", "BAND-B",
            "--exam-pass-rate", "1.0", "--lesson-yield", "1.0", "--retrieval-precision", "1.0",
            "--tasks-completed", "10", "--tasks-attempted", "10",
            "--verification-coverage", "1.0", "--performer-is-verifier",
        ],
        capsys,
    )
    payload = json.loads(out.out)
    assert code == 10
    assert payload["permitted"] is False
    assert payload["scorecard"]["V"] == 0.0


def test_score_permits_when_measurements_meet_thresholds(attestation_file, capsys):
    code, out = _run(
        [
            "--json", "--attestations", str(attestation_file), "score", "--band", "BAND-B",
            "--exam-pass-rate", "0.9", "--lesson-yield", "1.0", "--retrieval-precision", "1.0",
            "--tasks-completed", "9", "--tasks-attempted", "10",
            "--verification-coverage", "1.0",
        ],
        capsys,
    )
    assert code == 0
    assert json.loads(out.out)["permitted"] is True


def test_bad_registry_path_exits_two(capsys, tmp_path):
    code, _ = _run(["--registry", str(tmp_path / "absent.yaml"), "validate"], capsys)
    assert code == 2
