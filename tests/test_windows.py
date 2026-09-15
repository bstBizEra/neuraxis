"""Per-control attestation windows (v0.2).

A single global window forces every control onto the cadence of the cheapest
one. That is how expensive drills get stubbed, and a stubbed drill is a vacuous
check wearing a different hat — so each control carries its own window.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import yaml

from neuraxis import (
    Attestation,
    AttestationStore,
    AuthorityRequest,
    BandResolver,
    Decision,
    GovernanceGate,
    load_registry,
)
from neuraxis.errors import RegistryError
from neuraxis.model import now_utc


def _write(tmp_path, data):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _mixed_registry(tmp_path):
    """BAND-A needs a 24h control and a 30d control."""
    return _write(
        tmp_path,
        {
            "framework": "test",
            "version": "0.1",
            "governance": {
                "GV-01": {"name": "identity", "attestation": "x/y", "max_age": "24h"},
                "GV-05": {"name": "reversibility", "attestation": "x/drill", "max_age": "30d"},
                "GV-99": {"name": "defaulted", "attestation": "x/z"},
            },
            "capabilities": {
                "IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"}
            },
            "bands": {"BAND-A": {"requires": ["GV-01", "GV-05", "GV-99"], "depends_on": []}},
            "authority": {"role_grants": {"operator": ["BAND-A"]}},
            "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "12h"},
        },
    )


def _store(**ages: timedelta) -> AttestationStore:
    return AttestationStore(
        Attestation(
            control=control, result=True, issued_at=now_utc() - age,
            issuer="harness", evidence_ref=f"test://{control}",
        )
        for control, age in ages.items()
    )


# ---- parsing -----------------------------------------------------------


def test_bundled_registry_assigns_distinct_windows(registry):
    assert registry.max_age_for("GV-01") == timedelta(hours=24)
    assert registry.max_age_for("GV-04") == timedelta(days=7)
    assert registry.max_age_for("GV-05") == timedelta(days=30)


def test_control_without_max_age_inherits_the_registry_default(tmp_path):
    reg = load_registry(_mixed_registry(tmp_path))
    assert reg.max_age_for("GV-99") == timedelta(hours=12)
    assert reg.attestation_max_age == timedelta(hours=12)


def test_unknown_control_falls_back_to_default_rather_than_raising(registry):
    """Reached from the deny path; a lookup failure must not become an exception."""
    assert registry.max_age_for("GV-does-not-exist") == registry.attestation_max_age


def test_invalid_per_control_window_is_rejected(tmp_path):
    data = yaml.safe_load(_mixed_registry(tmp_path).read_text())
    data["governance"]["GV-01"]["max_age"] = "1 fortnight"
    with pytest.raises(RegistryError, match="invalid duration"):
        load_registry(_write(tmp_path, data))


# ---- resolution --------------------------------------------------------


def test_each_control_is_judged_against_its_own_window(tmp_path):
    reg = load_registry(_mixed_registry(tmp_path))
    # 3 days old: past GV-01's 24h window, well inside GV-05's 30d window.
    store = _store(
        **{"GV-01": timedelta(days=3), "GV-05": timedelta(days=3), "GV-99": timedelta(hours=1)}
    )
    status = BandResolver(reg, store).status("BAND-A")
    assert status.attained is False
    assert status.missing_controls == ("GV-01",), "only the 24h control should have expired"


def test_band_attained_when_every_control_is_inside_its_own_window(tmp_path):
    """Positive control: the mixed-window path can still say yes."""
    reg = load_registry(_mixed_registry(tmp_path))
    store = _store(
        **{"GV-01": timedelta(hours=2), "GV-05": timedelta(days=20), "GV-99": timedelta(hours=1)}
    )
    assert BandResolver(reg, store).status("BAND-A").attained is True


def test_long_window_control_still_expires_eventually(tmp_path):
    reg = load_registry(_mixed_registry(tmp_path))
    store = _store(
        **{"GV-01": timedelta(hours=1), "GV-05": timedelta(days=31), "GV-99": timedelta(hours=1)}
    )
    status = BandResolver(reg, store).status("BAND-A")
    assert status.missing_controls == ("GV-05",)


def test_explanation_cites_the_controls_own_window(tmp_path):
    reg = load_registry(_mixed_registry(tmp_path))
    store = _store(
        **{"GV-01": timedelta(days=3), "GV-05": timedelta(hours=1), "GV-99": timedelta(hours=1)}
    )
    reasons = " ".join(BandResolver(reg, store).status("BAND-A").reasons)
    assert "max 1d" in reasons, "reason must quote GV-01's own 24h window, not the 12h default"


# ---- gate integration --------------------------------------------------


def test_gate_honours_per_control_windows(registry):
    """A 6-day-old GV-04 holds (7d window); a 6-day-old GV-01 does not (24h)."""
    six_days = timedelta(days=6)
    store = AttestationStore(
        Attestation(
            control=cid, result=True,
            issued_at=now_utc() - (six_days if cid == "GV-04" else timedelta(hours=1)),
            issuer="harness", evidence_ref="test://x",
        )
        for cid in registry.controls
    )
    request = AuthorityRequest(
        intent="run pipeline", identity="agent-drafter", role="drafter",
        capability="IL-06", scope="bst-sa", verifier="github-ci", rollback_tested=True,
    )
    assert GovernanceGate(registry, store).evaluate(request).decision is Decision.ALLOW

    stale_identity = AttestationStore(
        Attestation(
            control=cid, result=True,
            issued_at=now_utc() - (six_days if cid == "GV-01" else timedelta(hours=1)),
            issuer="harness", evidence_ref="test://x",
        )
        for cid in registry.controls
    )
    verdict = GovernanceGate(registry, stale_identity).evaluate(request)
    assert verdict.decision is Decision.DENY
    assert "GV-01" in verdict.missing_controls


def test_missing_accepts_a_bare_timedelta_for_single_window_callers(registry):
    store = _store(**{"GV-01": timedelta(hours=1)})
    assert store.missing(["GV-01", "GV-02"], timedelta(hours=24)) == ("GV-02",)


def test_snapshot_uses_per_control_windows(registry):
    store = _store(**{"GV-01": timedelta(days=3), "GV-04": timedelta(days=3)})
    snap = store.snapshot(registry.max_age_for)
    assert snap["GV-01"] is False   # 24h window
    assert snap["GV-04"] is True    # 7d window
