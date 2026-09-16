"""Evidence records and the obligation loop (v0.7.0).

The gate was write-only before this: it issued verdicts and nothing recorded
them, so three obligations were labels rather than controls. These tests cover
the edge that closes, and the ways it can be lied to.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    Decision,
    EvidenceError,
    EvidenceRecord,
    EvidenceSink,
    GovernanceGate,
    audit_obligations,
    load_registry,
    record_decision,
)
from neuraxis.cli import main
from neuraxis.evidence import DischargeRecord, new_verdict_id

UTC = timezone.utc
NOW = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)


@pytest.fixture
def gate():
    registry = load_registry()
    store = AttestationStore(
        Attestation(c, True, datetime.now(UTC), "h", "r", provenance="provider")
        for c in registry.controls
    )
    return GovernanceGate(registry, store)


@pytest.fixture
def request_():
    return AuthorityRequest(
        intent="run pipeline", identity="agent-drafter", role="drafter",
        capability="IL-06", scope="bst-sa", verifier="github-ci", rollback_tested=True,
    )


# ---- recording ---------------------------------------------------------


def test_an_allow_is_recorded_with_what_it_owes(tmp_path, gate, request_):
    sink = EvidenceSink(tmp_path / "ev.jsonl")
    verdict, record = record_decision(sink, request_, gate.evaluate(request_))
    assert verdict.decision is Decision.ALLOW
    assert record is not None
    assert set(record.obligations) >= {"emit-evidence-record", "independent-verification"}
    written = json.loads((tmp_path / "ev.jsonl").read_text().strip())
    assert written["record"] == "evidence"
    assert written["verdict_id"] == record.verdict_id


def test_a_denial_is_recorded_too(tmp_path, registry, request_):
    """A blocked decision is evidence as much as a permitted one."""
    gate = GovernanceGate(registry, AttestationStore())
    sink = EvidenceSink(tmp_path / "ev.jsonl")
    verdict, record = record_decision(sink, request_, gate.evaluate(request_))
    assert verdict.decision is Decision.DENY
    assert record is not None and record.permitted is False


def test_an_allow_that_cannot_be_recorded_becomes_a_denial(tmp_path, gate, request_):
    """A permission that leaves no trace is the condition GV-03 rules out."""
    unwritable = tmp_path / "ev.jsonl"
    unwritable.mkdir()  # a directory cannot be appended to
    verdict, record = record_decision(
        EvidenceSink(unwritable), request_, gate.evaluate(request_)
    )
    assert verdict.decision is Decision.DENY
    assert record is None
    assert any("could not be recorded" in r for r in verdict.reasons)


def test_an_unrecordable_denial_stays_a_denial(tmp_path, registry, request_):
    """Nothing was permitted, so there is no untraced action to worry about."""
    gate = GovernanceGate(registry, AttestationStore())
    unwritable = tmp_path / "ev.jsonl"
    unwritable.mkdir()
    verdict, _ = record_decision(EvidenceSink(unwritable), request_, gate.evaluate(request_))
    assert verdict.decision is Decision.DENY


def test_no_sink_configured_changes_nothing(gate, request_):
    original = gate.evaluate(request_)
    verdict, record = record_decision(None, request_, original)
    assert verdict is original and record is None


def test_verdict_ids_are_unique_for_identical_requests(gate, request_):
    """A content hash would merge two real decisions into one record."""
    ids = {
        record_decision(None, request_, gate.evaluate(request_)) and new_verdict_id()
        for _ in range(50)
    }
    assert len(ids) == 50


# ---- the audit ---------------------------------------------------------


def _evidence(vid, obligations, decision="ALLOW", performer="agent-drafter", at=NOW):
    return {
        "record": "evidence", "verdict_id": vid, "at": at.isoformat(),
        "decision": decision, "capability": "IL-06", "band": "BAND-B",
        "identity": performer, "performer": performer, "role": "drafter",
        "scope": "s", "intent": "i", "obligations": obligations, "reasons": [],
    }


def _discharge(vid, obligation, by="github-ci"):
    return {
        "record": "discharge", "verdict_id": vid, "obligation": obligation,
        "at": NOW.isoformat(), "by": by, "evidence_ref": "ref",
    }


def test_an_allow_with_everything_paid_is_clean():
    """Positive control: the audit must be able to say yes."""
    audit = audit_obligations([
        _evidence("v1", ["emit-evidence-record"]),
        _discharge("v1", "emit-evidence-record"),
    ])
    assert audit.clean is True
    assert audit.discharged == 1 and audit.owed == 1


def test_an_unpaid_obligation_is_outstanding():
    audit = audit_obligations([_evidence("v1", ["emit-evidence-record", "tested-rollback"])])
    assert audit.clean is False
    assert {o.obligation for o in audit.outstanding} == {
        "emit-evidence-record", "tested-rollback"
    }


def test_a_denial_owes_nothing():
    """Counting a block's obligations would invent a debt never incurred."""
    audit = audit_obligations([_evidence("v1", ["emit-evidence-record"], decision="DENY")])
    assert audit.owed == 0 and audit.allowed == 0 and audit.clean is True


def test_self_discharge_is_a_fault():
    """NX-INV-2 applied to obligations."""
    audit = audit_obligations([
        _evidence("v1", ["emit-evidence-record"], performer="agent-drafter"),
        _discharge("v1", "emit-evidence-record", by="agent-drafter"),
    ])
    assert any("discharged by the performer" in f for f in audit.faults)
    assert audit.outstanding, "a self-discharge must not count as payment"


@pytest.mark.parametrize("by", ["Agent-Drafter", "agent-drafter ", " AGENT-DRAFTER"])
def test_self_discharge_comparison_is_stripped_and_case_folded(by):
    audit = audit_obligations([
        _evidence("v1", ["emit-evidence-record"], performer="agent-drafter"),
        _discharge("v1", "emit-evidence-record", by=by),
    ])
    assert any("discharged by the performer" in f for f in audit.faults)


def test_a_discharge_for_an_unknown_verdict_is_a_fault():
    """Forged payment, or a lost record. Both are faults."""
    audit = audit_obligations([_discharge("ghost", "emit-evidence-record")])
    assert any("unknown verdict" in f for f in audit.faults)


def test_a_discharge_for_an_obligation_not_owed_is_a_fault():
    audit = audit_obligations([
        _evidence("v1", ["emit-evidence-record"]),
        _discharge("v1", "human-ratification"),
    ])
    assert any("not owed" in f for f in audit.faults)


def test_a_duplicate_verdict_id_is_a_fault():
    audit = audit_obligations([
        _evidence("v1", ["emit-evidence-record"]),
        _evidence("v1", []),
    ])
    assert any("duplicate verdict_id" in f for f in audit.faults)


def test_an_unrecognised_record_kind_is_a_fault():
    audit = audit_obligations([{"record": "something-else"}])
    assert audit.faults


def test_a_naive_timestamp_is_a_fault():
    audit = audit_obligations([
        {**_evidence("v1", ["emit-evidence-record"]), "at": "2026-09-16T08:00:00"}
    ])
    assert any("no timezone offset" in f for f in audit.faults)


def test_grace_excludes_obligations_too_recent_to_be_overdue():
    fresh = datetime.now(UTC)
    records = [_evidence("v1", ["emit-evidence-record"], at=fresh)]
    assert audit_obligations(records, grace=timedelta(hours=1)).outstanding == ()
    assert audit_obligations(records).outstanding != ()


# ---- sink io -----------------------------------------------------------


def test_absent_sink_reads_as_empty(tmp_path):
    assert list(EvidenceSink(tmp_path / "nothing.jsonl").read()) == []


def test_malformed_sink_raises_rather_than_skipping(tmp_path):
    path = tmp_path / "ev.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(EvidenceError):
        list(EvidenceSink(path).read())


def test_records_round_trip(tmp_path):
    sink = EvidenceSink(tmp_path / "ev.jsonl")
    sink.append(
        EvidenceRecord(
            verdict_id="v1", at=NOW, decision="ALLOW", capability="IL-06", band="BAND-B",
            identity="a", performer="a", role="drafter", scope="s", intent="i",
            obligations=("emit-evidence-record",), reasons=(),
        )
    )
    sink.append(DischargeRecord("v1", "emit-evidence-record", NOW, "ci", "ref"))
    kinds = [r["record"] for r in sink.read()]
    assert kinds == ["evidence", "discharge"]


# ---- cli ---------------------------------------------------------------


def _run(argv, capsys):
    code = main(argv)
    return code, capsys.readouterr()


@pytest.fixture
def attested(tmp_path, capsys):
    store = tmp_path / "att.jsonl"
    for control in ("GV-01", "GV-02", "GV-03", "GV-04", "GV-05"):
        main(["--attestations", str(store), "attest", "--control", control,
              "--result", "pass", "--issuer", "op", "--evidence-ref", "m"])
    capsys.readouterr()
    return store


def test_gate_reports_the_verdict_id_and_appends(tmp_path, attested, capsys):
    sink = tmp_path / "ev.jsonl"
    code, out = _run(
        ["--json", "--attestations", str(attested), "--evidence-sink", str(sink), "gate",
         "--capability", "IL-06", "--identity", "agent-drafter", "--role", "drafter",
         "--intent", "run", "--verifier", "github-ci", "--rollback-tested"],
        capsys,
    )
    payload = json.loads(out.out)
    assert code == 0 and payload["decision"] == "ALLOW"
    assert payload["verdict_id"]
    assert sink.is_file()


def test_obligations_exits_nonzero_while_anything_is_outstanding(tmp_path, attested, capsys):
    sink = tmp_path / "ev.jsonl"
    _run(["--attestations", str(attested), "--evidence-sink", str(sink), "gate",
          "--capability", "IL-06", "--identity", "a", "--role", "drafter",
          "--intent", "run", "--verifier", "ci", "--rollback-tested"], capsys)
    code, out = _run(["--json", "--evidence-sink", str(sink), "obligations"], capsys)
    assert code == 10
    assert json.loads(out.out)["clean"] is False


def test_discharge_refuses_a_verdict_that_was_never_issued(tmp_path, capsys):
    sink = tmp_path / "ev.jsonl"
    sink.write_text("", encoding="utf-8")
    code, _ = _run(
        ["--evidence-sink", str(sink), "discharge", "--verdict", "ghost",
         "--obligation", "emit-evidence-record", "--by", "ci", "--evidence-ref", "r"],
        capsys,
    )
    assert code == 2


def test_discharge_and_obligations_close_the_loop(tmp_path, attested, capsys):
    sink = tmp_path / "ev.jsonl"
    _run(["--json", "--attestations", str(attested), "--evidence-sink", str(sink), "gate",
          "--capability", "IL-06", "--identity", "agent-drafter", "--role", "drafter",
          "--intent", "run", "--verifier", "ci", "--rollback-tested"], capsys)
    vid = [
        r["verdict_id"] for r in EvidenceSink(sink).read() if r["record"] == "evidence"
    ][-1]
    for obligation in ("emit-evidence-record", "independent-verification", "tested-rollback"):
        code, _ = _run(
            ["--evidence-sink", str(sink), "discharge", "--verdict", vid,
             "--obligation", obligation, "--by", "github-ci", "--evidence-ref", "r"],
            capsys,
        )
        assert code == 0
    code, out = _run(["--json", "--evidence-sink", str(sink), "obligations"], capsys)
    assert code == 0
    assert json.loads(out.out)["clean"] is True


def test_obligations_requires_a_sink(capsys):
    code, _ = _run(["obligations"], capsys)
    assert code == 2
