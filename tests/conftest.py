from __future__ import annotations

from datetime import timedelta

import pytest

from neuraxis import Attestation, AttestationStore, AuthorityRequest, load_registry
from neuraxis.model import now_utc


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def empty_store():
    return AttestationStore()


def _attest_all(registry, *, age=timedelta(0), result=True) -> AttestationStore:
    issued = now_utc() - age
    return AttestationStore(
        Attestation(
            control=control,
            result=result,
            issued_at=issued,
            issuer="test-harness",
            evidence_ref=f"test://{control}",
        )
        for control in registry.controls
    )


@pytest.fixture
def full_store(registry):
    """Every governance control currently passing."""
    return _attest_all(registry)


@pytest.fixture
def attest_all():
    return _attest_all


@pytest.fixture
def valid_request():
    """A BAND-B request that should ALLOW under a fully attested store.

    This is the positive control. Without it, every deny-assertion in this
    suite would also pass against a gate that denies unconditionally.
    """
    return AuthorityRequest(
        intent="run the coffee cost calculator pipeline",
        identity="agent-drafter",
        role="drafter",
        capability="IL-06",
        scope="bst-sa/pipelines",
        verifier="github-ci",
        rollback_tested=True,
    )
