from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from neuraxis import Attestation, AttestationStore
from neuraxis.errors import AttestationError
from neuraxis.model import now_utc

DAY = timedelta(hours=24)


def _att(control="GV-01", *, result=True, age=timedelta(0), ref="test://ref"):
    return Attestation(
        control=control,
        result=result,
        issued_at=now_utc() - age,
        issuer="harness",
        evidence_ref=ref,
    )


def test_fresh_passing_attestation_holds():
    store = AttestationStore([_att()])
    assert store.holds("GV-01", DAY) is True


def test_absent_attestation_does_not_hold():
    assert AttestationStore().holds("GV-01", DAY) is False


def test_failing_attestation_does_not_hold():
    store = AttestationStore([_att(result=False)])
    assert store.holds("GV-01", DAY) is False
    assert "FAILED" in store.explain("GV-01", DAY)


def test_expired_attestation_does_not_hold():
    store = AttestationStore([_att(age=timedelta(hours=25))])
    assert store.holds("GV-01", DAY) is False
    assert "expired" in store.explain("GV-01", DAY)


def test_attestation_exactly_at_max_age_still_holds():
    """Boundary is inclusive; tested so a later refactor cannot silently flip it.

    `at` is pinned rather than defaulted: computing it from the wall clock makes
    the age marginally greater than max_age and the assertion meaningless.
    """
    att = _att(age=DAY)
    store = AttestationStore([att])
    assert store.holds("GV-01", DAY, at=att.issued_at + DAY) is True
    assert store.holds("GV-01", DAY, at=att.issued_at + DAY + timedelta(seconds=1)) is False


def test_future_dated_attestation_is_rejected():
    """A clock pushed forward must not keep a dead attestation alive."""
    store = AttestationStore([_att(age=timedelta(hours=-5))])
    assert store.holds("GV-01", DAY) is False
    assert "future-dated" in store.explain("GV-01", DAY)


def test_newer_failure_supersedes_older_pass():
    store = AttestationStore([
        _att(age=timedelta(hours=2), result=True),
        _att(age=timedelta(hours=1), result=False),
    ])
    assert store.holds("GV-01", DAY) is False


def test_older_failure_does_not_override_newer_pass():
    store = AttestationStore([
        _att(age=timedelta(hours=2), result=False),
        _att(age=timedelta(hours=1), result=True),
    ])
    assert store.holds("GV-01", DAY) is True


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="tz-aware"):
        Attestation(
            control="GV-01",
            result=True,
            issued_at=datetime(2026, 1, 1),  # noqa: DTZ001 - deliberate
            issuer="harness",
            evidence_ref="x",
        )


def test_missing_reports_every_absent_control():
    store = AttestationStore([_att("GV-01")])
    assert store.missing(["GV-01", "GV-02", "GV-03"], DAY) == ("GV-02", "GV-03")


def test_roundtrip_through_file(tmp_path):
    path = tmp_path / "attestations.jsonl"
    store = AttestationStore()
    store.append_to_file(path, _att("GV-01"))
    store.append_to_file(path, _att("GV-02", result=False))

    reloaded = AttestationStore.from_file(path)
    assert reloaded.holds("GV-01", DAY) is True
    assert reloaded.holds("GV-02", DAY) is False


def test_absent_file_yields_empty_store_not_an_error(tmp_path):
    store = AttestationStore.from_file(tmp_path / "nothing.jsonl")
    assert len(store) == 0


def test_malformed_line_raises_rather_than_being_skipped(tmp_path):
    """Skipping a bad line could skip a FAIL and leave a band open."""
    path = tmp_path / "attestations.jsonl"
    path.write_text(json.dumps({"control": "GV-01"}) + "\n", encoding="utf-8")
    with pytest.raises(AttestationError):
        AttestationStore.from_file(path)


def test_comments_and_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "attestations.jsonl"
    payload = {
        "control": "GV-01", "result": True, "issued_at": now_utc().isoformat(),
        "issuer": "h", "evidence_ref": "r",
    }
    path.write_text("# header\n\n" + json.dumps(payload) + "\n", encoding="utf-8")
    assert AttestationStore.from_file(path).holds("GV-01", DAY) is True
