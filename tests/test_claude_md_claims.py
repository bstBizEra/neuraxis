"""CLAUDE.md names the mechanism behind each rule. This checks they exist.

The first version of that section claimed two of seven items were mechanised
and "the rest are enforced by nothing but this file". By the end of the same
day five of the seven were, and the sentence had quietly become false. It was
corrected by hand — which is the move this repository distrusts everywhere
else, so the corrected version is pinned here instead.

The failure this prevents is specific and silent: someone renames
`_check_verifier_independence`, every test still passes because the gate's
behaviour is unchanged, and CLAUDE.md goes on telling readers that a function
which no longer exists is what enforces NX-INV-2. The document does not break.
It just stops being true, and the next agent reads it anyway.

This does not check that the mechanisms WORK — their own suites do that. It
checks that the thing CLAUDE.md points at is still there to point at.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8-sig")


def test_the_enforcement_table_is_still_there():
    """If this section is removed or retitled, the tests below are vacuous."""
    assert "### What actually enforces each of these" in CLAUDE_MD
    assert "What is genuinely unenforced" in CLAUDE_MD


# --- each mechanism the table names ----------------------------------------


def test_the_kernel_guard_exists_and_is_installed():
    assert (REPO_ROOT / ".claude" / "hooks" / "kernel_guard.py").is_file()
    assert "kernel_guard" in (REPO_ROOT / ".claude" / "settings.json").read_text(
        encoding="utf-8-sig"
    )


def test_the_verifier_independence_check_exists():
    from neuraxis.gate import GovernanceGate

    assert hasattr(GovernanceGate, "_check_verifier_independence"), (
        "CLAUDE.md names gate.py:_check_verifier_independence as what enforces NX-INV-2"
    )


def test_the_drill_runner_still_refuses_to_name_a_verifier():
    """The table claims it has no flag to set `verifier`. That is the whole
    reason GV-05 cannot be self-attested, so it is asserted rather than
    described."""
    source = (REPO_ROOT / "scripts" / "rollback_drill.py").read_text(encoding="utf-8-sig")
    assert "--verifier" not in source
    assert "--verify" in source, "the honest verification path is gone"


def test_the_waiver_bounds_exist_and_cannot_be_widened():
    from neuraxis.waiver import MAX_TTL_CEILING, NON_COMPENSABLE_FLOOR, WaiverPolicy

    assert NON_COMPENSABLE_FLOOR, "the non-compensable set is empty"
    # The table's claim is specifically that config may TIGHTEN and never
    # widen. A policy that tried to do both is the test of it.
    from datetime import timedelta

    relaxed = WaiverPolicy(non_compensable=frozenset(), max_ttl=timedelta(days=3650))
    assert NON_COMPENSABLE_FLOOR <= relaxed.non_compensable, "the floor was shrunk by config"
    assert relaxed.max_ttl <= MAX_TTL_CEILING, "the ceiling was widened by config"


def test_a_waiver_never_licenses_its_own_issuer_or_the_accountable_party():
    from neuraxis.waiver import Waiver

    assert hasattr(Waiver, "principals"), (
        "CLAUDE.md names Waiver.principals as what stops a self-licensing waiver"
    )


def test_the_assist_classifier_is_reachable():
    """Item 5 says seats are decided mechanically rather than by reading."""
    from neuraxis import biztrust

    assert hasattr(biztrust, "assist")
    assert (REPO_ROOT / "docs" / "BIZTRUST-ASSIST.md").is_file()


def test_the_skip_guard_exists():
    spec = importlib.util.spec_from_file_location(
        "conftest_under_test", REPO_ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.skip_verdict)


# --- the honest edge --------------------------------------------------------


def test_the_document_still_admits_what_is_not_enforced():
    """The most valuable line in the section is the one naming the gap.

    An enforcement table with no gap reads as completeness, and a reader who
    believes it stops looking for the hole. Identity is the hole.
    """
    for claim in ("identity", "unauthenticated", "T1 gap"):
        assert claim in CLAUDE_MD, f"CLAUDE.md no longer names {claim!r} as the open gap"


def test_item_seven_is_still_described_as_partial():
    """A skipped test is caught; a weakened assertion is not. If that ever
    reads as fully enforced without a mechanism appearing, the table has
    started flattering itself."""
    assert "weakened assertion" in CLAUDE_MD or "weakened* assertion" in CLAUDE_MD
