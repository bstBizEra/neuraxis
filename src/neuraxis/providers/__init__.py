"""Attestation providers.

An attestation recorded by hand (`neuraxis attest --result pass`) is an
operator asserting something. A provider is a check that *establishes* it and
cites the evidence. Until providers exist, the gate is well-built theatre.

Every provider runs through `harness.run_provider`, which enforces four rules
carried over from the KBS-001 adversarial review, where three of five probes
passed unconditionally:

  1. Fail closed      — any unexpected condition is FAIL, never PASS
  2. Positive control — prove the check is live before scoring a negative
  3. Vacuity probe    — prove the check can fail, by running it against a
                        condition that must fail
  4. Evidence         — a bare pass/fail is not an attestation

A provider that cannot satisfy all four does not get to record a PASS.
"""

from __future__ import annotations

from .base import Provider, ProviderOutcome, ProviderResult, UnwiredProvider
from .harness import ConformanceError, run_provider
from .registry import PROVIDERS, get_provider, providers_for, register

__all__ = [
    "PROVIDERS",
    "ConformanceError",
    "Provider",
    "ProviderOutcome",
    "ProviderResult",
    "UnwiredProvider",
    "get_provider",
    "providers_for",
    "register",
    "run_provider",
]
