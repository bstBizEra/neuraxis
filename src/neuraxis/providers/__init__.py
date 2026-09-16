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

**What the four rules do not establish.** Rule 3 runs a probe the provider
itself authors, so it proves a probe exists and reports failure — not that the
probe exercised the same code path as `check()`. A provider with a canned
failing probe and a canned passing check satisfies every rule. No in-process
harness can close that: provider integrity belongs to the kernel boundary
(signed manifests, out-of-process execution), which is KBS-001's job, not this
module's. See "known limits" in the README.
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
