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


# --- a skipped test in CI is a test that did not run ------------------------
#
# 93 of this suite's tests sit behind `pytest.skip("git is not available")`:
# the drill runner's refusals, the ratification-gap check, and the whole
# assist classifier. The guard is right for a developer machine without git.
# In CI it is a hole: if git were missing or broken on a runner, a tenth of
# the suite would vanish and the run would still report green.
#
# That is the failure this package exists to prevent, and this suite had it.
# A check that silently does not run is worse than no check, because the green
# is read as evidence.
#
# So under CI, a skip is a failure. There is no allowlist: today the suite
# skips nothing on any runner in the matrix, and the moment a legitimate
# environment skip appears, the right response is to argue for it in a diff
# rather than to let it join a list nobody rereads.


def skip_verdict(*, in_ci: bool, skipped: list[tuple[str, str]]) -> str | None:
    """The decision, separated from the wiring so it can be tested directly.

    Returns the failure message, or None if the run is acceptable.
    """
    if not in_ci or not skipped:
        return None
    lines = [f"{len(skipped)} test(s) skipped under CI, so they did not run:"]
    lines += [f"  {nodeid}: {reason or '<no reason given>'}" for nodeid, reason in skipped[:20]]
    if len(skipped) > 20:
        lines.append(f"  ... and {len(skipped) - 20} more")
    lines.append(
        "A skip in CI means the runner is not the environment CI claims to be. "
        "Fix the environment, or argue for the skip in a diff."
    )
    return "\n".join(lines)


_SKIPPED: list[tuple[str, str]] = []


def pytest_runtest_logreport(report):  # noqa: D103
    if report.skipped:
        reason = ""
        if isinstance(getattr(report, "longrepr", None), tuple) and len(report.longrepr) == 3:
            reason = str(report.longrepr[2]).removeprefix("Skipped: ")
        _SKIPPED.append((report.nodeid, reason))


def pytest_sessionfinish(session, exitstatus):  # noqa: D103
    import os

    message = skip_verdict(in_ci=bool(os.environ.get("CI")), skipped=_SKIPPED)
    if message is None:
        return
    print("\n" + message)
    session.exitstatus = 1
