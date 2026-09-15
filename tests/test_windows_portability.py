"""Windows portability.

Every one of these was found by running the suite on the real target rather
than in the build environment. A BOM on line 1 fails closed, which looks like
the system working — the provider reports "not live" and the band stays shut —
but the cause is an encoding detail, not the control it claims to be checking.
A correct answer for the wrong reason is still a defect.
"""

from __future__ import annotations

import json

import yaml

from neuraxis import AttestationStore, load_registry
from neuraxis.providers import run_provider
from neuraxis.providers.builtin import VerifierIndependenceProvider
from neuraxis.model import now_utc

BOM = "﻿"


def _write_bom(path, text: str):
    """Write as PowerShell's `Out-File -Encoding utf8` does on Windows 5.1."""
    path.write_bytes((BOM + text).encode("utf-8"))
    return path


# ---- task log ----------------------------------------------------------


def test_task_log_with_a_bom_is_readable(tmp_path):
    path = _write_bom(
        tmp_path / "task-log.jsonl",
        "\n".join(
            json.dumps(r)
            for r in [
                {"task_id": "t1", "performer": "agent-drafter", "verifier": "github-ci"},
                {"task_id": "t2", "performer": "agent-motor", "verifier": "github-ci"},
            ]
        ),
    )
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is True, "a BOM must not make the check report 'not live'"
    assert run.result.facts["sampled"] == 2


def test_bom_does_not_mask_a_real_breach(tmp_path):
    """The fix must not turn a genuine failure into a pass."""
    path = _write_bom(
        tmp_path / "task-log.jsonl",
        json.dumps({"task_id": "t1", "performer": "agent-cortex", "verifier": "agent-cortex"}),
    )
    run = run_provider(VerifierIndependenceProvider(log_path=path))
    assert run.attests is False
    assert "verifier equals performer" in run.result.detail


# ---- attestation store -------------------------------------------------


def test_attestation_file_with_a_bom_loads(tmp_path):
    payload = {
        "control": "GV-01", "result": True, "issued_at": now_utc().isoformat(),
        "issuer": "operator", "evidence_ref": "kbs-001/run-1",
    }
    path = _write_bom(tmp_path / "attestations.jsonl", json.dumps(payload))
    store = AttestationStore.from_file(path)
    assert store.get("GV-01") is not None


# ---- registry ----------------------------------------------------------


def test_registry_with_a_bom_loads(tmp_path):
    data = {
        "framework": "test",
        "version": "0.1",
        "governance": {"GV-01": {"name": "identity", "attestation": "x/y"}},
        "capabilities": {"IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"}},
        "bands": {"BAND-A": {"requires": ["GV-01"], "depends_on": []}},
        "authority": {"role_grants": {"operator": ["BAND-A"]}},
        "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "24h"},
    }
    path = _write_bom(tmp_path / "neuraxis.yaml", yaml.safe_dump(data))
    assert load_registry(path).framework == "test"


# ---- console encoding --------------------------------------------------


def test_human_output_keeps_non_ascii_intact(capsys):
    """Provider text contains em-dashes; a cp1252 console must not mangle them."""
    from neuraxis.cli import main

    code = main(["providers"])
    out = capsys.readouterr().out
    assert code == 0
    assert "—" in out, "em-dash in blocked_on text must survive the output path"


def test_json_output_escapes_non_ascii(capsys):
    """The machine contract stays pure ASCII on the wire.

    `\u2014` is valid JSON and survives any transport or console encoding, so
    escaping here is correct rather than a portability gap — the human-readable
    path is where the literal character has to come through.
    """
    from neuraxis.cli import main

    main(["--json", "providers"])
    out = capsys.readouterr().out
    assert out.isascii()
    assert "\\u2014" in out
    assert json.loads(out)["controls"]["GV-01"]["blocked_on"].count("—") == 1


def test_force_utf8_io_tolerates_a_stream_without_reconfigure(monkeypatch):
    """pytest and some runners replace stdout with an object lacking reconfigure."""
    import sys

    from neuraxis.cli import _force_utf8_io

    class Bare:
        pass

    monkeypatch.setattr(sys, "stdout", Bare())
    monkeypatch.setattr(sys, "stderr", Bare())
    _force_utf8_io()  # must not raise


def test_force_utf8_io_tolerates_a_stream_that_refuses(monkeypatch):
    import sys

    from neuraxis.cli import _force_utf8_io

    class Refusing:
        def reconfigure(self, **_kwargs):
            raise ValueError("stream is detached")

    monkeypatch.setattr(sys, "stdout", Refusing())
    monkeypatch.setattr(sys, "stderr", Refusing())
    _force_utf8_io()  # must not raise
