"""Capability guard — the call-site enforcement point.

Two forms, same semantics:

    with guard.require(request):          # raises CapabilityDenied on non-ALLOW
        do_the_thing()

    @guard.capability("IL-11", role="cortex")
    def extract_lesson(...): ...

The guard exists so that enforcement is structural rather than remembered. A
caller that forgets to check a verdict cannot proceed, because the guard raises
instead of returning a falsy value that might be ignored.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

from .attestation import AttestationStore
from .errors import NeuraxisError
from .gate import GovernanceGate
from .model import AuthorityRequest, Risk, Verdict
from .registry import Registry

F = TypeVar("F", bound=Callable[..., Any])


class CapabilityDenied(NeuraxisError):
    """Raised when the gate does not return ALLOW.

    Carries the verdict so the caller can route on DELEGATE / ESCALATE /
    WAIT_FOR_AUTHORITY rather than treating every block as a failure.
    """

    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        reasons = "; ".join(verdict.reasons) or "no reason recorded"
        super().__init__(f"{verdict.decision.value} {verdict.capability}: {reasons}")


class CapabilityGuard:
    """Wraps a gate with call-site ergonomics."""

    def __init__(self, registry: Registry, attestations: AttestationStore) -> None:
        self.gate = GovernanceGate(registry, attestations)

    def check(self, request: AuthorityRequest) -> Verdict:
        """Evaluate without raising. Use when you need to route on the verdict."""
        return self.gate.evaluate(request)

    @contextmanager
    def require(self, request: AuthorityRequest) -> Iterator[Verdict]:
        """Block unless the gate allows. Yields the verdict with its obligations."""
        verdict = self.gate.evaluate(request)
        if not verdict.permits_action:
            raise CapabilityDenied(verdict)
        yield verdict

    def capability(
        self,
        capability_id: str,
        *,
        role: str,
        identity: str | None = None,
        scope: str = "default",
        risk: Risk = Risk.LOW,
        verifier: str | None = None,
        rollback_tested: bool = False,
    ) -> Callable[[F], F]:
        """Decorator form. The wrapped function runs only on ALLOW.

        `intent` defaults to the function's qualified name, which keeps the
        evidence record meaningful without extra ceremony at the call site.
        """

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                request = AuthorityRequest(
                    intent=f"{func.__module__}.{func.__qualname__}",
                    identity=identity or role,
                    role=role,
                    capability=capability_id,
                    scope=scope,
                    risk=risk,
                    verifier=verifier,
                    rollback_tested=rollback_tested,
                )
                with self.require(request):
                    return func(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorator
