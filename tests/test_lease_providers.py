"""GV-02 authority and GV-06 containment (v0.5.2).

Both audits recompute from raw lease and action records rather than trusting a
tally L0 emits about itself — a self-reported compliance count is the
performer-verifies-itself failure moved to the evidence layer.

Each breach class has its own test, paired with a clean-log positive control.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from neuraxis.providers import ProviderOutcome, providers_for, run_provider
from neuraxis.providers.lease import LeaseAuthorityProvider, LeaseContainmentProvider

UTC = timezone.utc
T0 = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


def lease(**over):
    base = {
        "record": "lease",
        "lease_id": "L-0031",
        "principal": "agent-motor",
        "issued_by": "l0-gate",
        "issued_at": T0.isoformat(),
        "expires_at": (T0 + timedelta(hours=1)).isoformat(),
        "scope": ["repo:bstBizEra/secb_pf", "tool:git"],
        "ceilings": {"tokens": 200000, "wall_seconds": 900},
        "consumed": {"tokens": 143221, "wall_seconds": 410},
        "ceilings_amended_by": None,
    }
    base.update(over)
    return base


def action(**over):
    base = {
        "record": "action",
        "action_id": "a-1",
        "lease_id": "L-0031",
        "at": (T0 + timedelta(minutes=12)).isoformat(),
        "scope": "tool:git",
    }
    base.update(over)
    return base


def _log(tmp_path, records, bom=False):
    path = tmp_path / "lease-log.jsonl"
    text = "\n".join(json.dumps(r) for r in records)
    path.write_bytes((("﻿" if bom else "") + text).encode("utf-8"))
    return path


def auth(tmp_path, records, **kw):
    return run_provider(LeaseAuthorityProvider(lease_log_path=_log(tmp_path, records, **kw)))


def contain(tmp_path, records, **kw):
    return run_provider(LeaseContainmentProvider(lease_log_path=_log(tmp_path, records, **kw)))


# ======================= GV-02 authority ================================


def test_authority_passes_on_a_clean_log(tmp_path):
    """POSITIVE CONTROL for GV-02."""
    run = auth(tmp_path, [lease(), action(), action(action_id="a-2", scope="repo:bstBizEra/secb_pf")])
    assert run.attests is True
    assert run.result.facts["sampled"] == 2
    assert run.result.facts["leases"] == 1


def test_action_with_no_lease_claimed(tmp_path):
    run = auth(tmp_path, [lease(), action(lease_id=None)])
    assert run.attests is False
    assert "no lease claimed" in run.result.detail


def test_action_claiming_a_lease_not_in_the_log(tmp_path):
    run = auth(tmp_path, [lease(), action(lease_id="L-ghost")])
    assert run.attests is False
    assert "not in the log" in run.result.detail


def test_action_executed_before_its_lease_was_issued(tmp_path):
    """Post-hoc authorisation: the record is complete, the act was not authorised."""
    run = auth(tmp_path, [lease(), action(at=(T0 - timedelta(minutes=30)).isoformat())])
    assert run.attests is False
    assert "before lease L-0031 was issued" in run.result.detail


def test_action_executed_after_expiry(tmp_path):
    run = auth(tmp_path, [lease(), action(at=(T0 + timedelta(hours=3)).isoformat())])
    assert run.attests is False
    assert "after lease L-0031 expired" in run.result.detail


def test_action_outside_granted_scope(tmp_path):
    run = auth(tmp_path, [lease(), action(scope="tool:kubectl")])
    assert run.attests is False
    assert "outside lease L-0031" in run.result.detail


def test_self_issued_lease(tmp_path):
    """A component that can grant itself authority has none."""
    run = auth(tmp_path, [lease(issued_by="agent-motor"), action()])
    assert run.attests is False
    assert "self-issued by agent-motor" in run.result.detail


def test_standing_lease_with_no_expiry(tmp_path):
    run = auth(tmp_path, [lease(expires_at=None), action()])
    assert run.attests is False
    assert "standing lease, no expiry" in run.result.detail


def test_lease_with_empty_scope_bounds_nothing(tmp_path):
    run = auth(tmp_path, [lease(scope=[]), action()])
    assert run.attests is False
    assert "bounds nothing" in run.result.detail


def test_duplicate_lease_id(tmp_path):
    run = auth(tmp_path, [lease(), lease(), action()])
    assert run.attests is False
    assert "duplicate lease id" in run.result.detail


def test_naive_timestamp_in_the_lease_log_is_a_breach(tmp_path):
    run = auth(tmp_path, [lease(), action(at="2026-09-14T08:12:00")])
    assert run.attests is False
    assert "no timezone offset" in run.result.detail


def test_authority_positive_control_needs_actions(tmp_path):
    """Leases with no actions is no evidence that actions were authorised."""
    run = auth(tmp_path, [lease()])
    assert run.attests is False
    assert "positive-control-failed" in run.conformance


def test_authority_vacuity_probe_fails_as_required(tmp_path):
    provider = LeaseAuthorityProvider(lease_log_path=tmp_path / "x.jsonl")
    assert provider.vacuity_probe().outcome is ProviderOutcome.FAIL


# ======================= GV-06 containment ==============================


def test_containment_passes_on_a_clean_log(tmp_path):
    """POSITIVE CONTROL for GV-06."""
    run = contain(tmp_path, [lease(), lease(lease_id="L-0032")])
    assert run.attests is True
    assert run.result.facts["sampled"] == 2


def test_lease_with_no_ceilings_is_unbounded(tmp_path):
    run = contain(tmp_path, [lease(ceilings={})])
    assert run.attests is False
    assert "unbounded grant" in run.result.detail


def test_ceiling_exceeded_means_it_was_advisory(tmp_path):
    """The point of the control: a recorded limit that was not applied."""
    run = contain(tmp_path, [lease(consumed={"tokens": 250000, "wall_seconds": 410})])
    assert run.attests is False
    assert "tokens consumed 250000 over ceiling 200000" in run.result.detail


def test_consuming_a_resource_with_no_ceiling(tmp_path):
    """Bounded on tokens, unbounded on everything else."""
    run = contain(tmp_path, [lease(consumed={"tokens": 10, "network_bytes": 999})])
    assert run.attests is False
    assert "no ceiling declared for it" in run.result.detail


def test_ceilings_widened_by_the_principal_they_bound(tmp_path):
    run = contain(tmp_path, [lease(ceilings_amended_by="agent-motor")])
    assert run.attests is False
    assert "widened by the principal they bound" in run.result.detail


def test_ceilings_widened_by_someone_else_is_permitted_here(tmp_path):
    """Self-amendment is the breach; an authorised widening is not GV-06's call."""
    run = contain(tmp_path, [lease(ceilings_amended_by="ounkhamvilay")])
    assert run.attests is True


def test_non_numeric_consumption_is_a_breach(tmp_path):
    run = contain(tmp_path, [lease(consumed={"tokens": "lots"})])
    assert run.attests is False
    assert "not numeric" in run.result.detail


def test_consumption_exactly_at_the_ceiling_passes(tmp_path):
    """Boundary is inclusive; pinned so a refactor cannot silently flip it."""
    run = contain(tmp_path, [lease(consumed={"tokens": 200000, "wall_seconds": 900})])
    assert run.attests is True


def test_containment_positive_control_needs_leases(tmp_path):
    run = contain(tmp_path, [action()])
    assert run.attests is False
    assert "positive-control-failed" in run.conformance


def test_containment_vacuity_probe_fails_as_required(tmp_path):
    provider = LeaseContainmentProvider(lease_log_path=tmp_path / "x.jsonl")
    assert provider.vacuity_probe().outcome is ProviderOutcome.FAIL


# ======================= shared behaviour ===============================


@pytest.mark.parametrize("runner", [auth, contain])
def test_absent_log_fails_the_positive_control(tmp_path, runner):
    provider = (LeaseAuthorityProvider if runner is auth else LeaseContainmentProvider)(
        lease_log_path=tmp_path / "absent.jsonl"
    )
    run = run_provider(provider)
    assert run.attests is False
    assert "positive-control-failed" in run.conformance


@pytest.mark.parametrize("runner", [auth, contain])
def test_unclassified_record_fails_rather_than_narrowing_the_sample(tmp_path, runner):
    """A record of neither kind must not be silently dropped."""
    run = runner(tmp_path, [lease(), action(), {"something": "else"}])
    assert run.attests is False


@pytest.mark.parametrize("runner", [auth, contain])
def test_malformed_log_fails(tmp_path, runner):
    path = tmp_path / "lease-log.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    provider = (LeaseAuthorityProvider if runner is auth else LeaseContainmentProvider)(
        lease_log_path=path
    )
    assert run_provider(provider).attests is False


def test_bom_does_not_break_either_check(tmp_path):
    assert auth(tmp_path, [lease(), action()], bom=True).attests is True
    assert contain(tmp_path, [lease()], bom=True).attests is True


def test_bom_does_not_mask_a_real_breach(tmp_path):
    run = auth(tmp_path, [lease(issued_by="agent-motor"), action()], bom=True)
    assert run.attests is False


def test_one_breach_fails_the_whole_sample(tmp_path):
    run = auth(tmp_path, [lease(), action(), action(action_id="bad", scope="tool:kubectl")])
    assert run.attests is False
    assert run.result.facts["breaches"] == 1
    assert run.result.facts["sampled"] == 2


# ======================= registry =======================================


def test_gv_02_and_gv_06_are_wired():
    for control, name in [("GV-02", "l0/lease-audit"), ("GV-06", "l0/scope-budget")]:
        found = providers_for(control)
        assert [p.name for p in found] == [name]
        assert not hasattr(found[0], "blocked_on"), f"{control} should no longer be unwired"


def test_both_read_the_same_log(tmp_path):
    """One export, two audits — two exports would be two things that must agree."""
    path = _log(tmp_path, [lease(), action()])
    assert run_provider(LeaseAuthorityProvider(lease_log_path=path)).attests is True
    assert run_provider(LeaseContainmentProvider(lease_log_path=path)).attests is True
