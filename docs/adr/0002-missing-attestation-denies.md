# 0002 — A missing attestation denies, and there is no partial registry

**Status:** Accepted · **Date:** 2026-09-10

## Context

Every governance system has to answer what happens when the evidence is absent
rather than negative. The tempting answer is that absence is neutral: nothing
has failed, so nothing is blocked.

That answer is how governance systems die quietly. A probe that stops running
emits nothing, not FAIL. A provider whose evidence file is missing emits
nothing. A control nobody wired emits nothing. Under "absence is neutral" the
system reports green while measuring less and less, and the moment of discovery
is an audit rather than an alert.

## Decision

**Missing is denied.** An unattested control blocks its bands. A stale
attestation — past its window — is missing. A wired control with no evidence
source fails rather than being skipped. A registry that fails any invariant does
not load at all; there is no partial or default registry.

Attestation freshness is per control, not global: the kernel boundary probe is
cheap and should run daily, a rollback drill is disruptive and forcing it daily
guarantees it gets stubbed. A stubbed drill is a vacuous probe, which is worse
than an honest gap.

## Consequences

**The initial state is that everything is blocked, and that is correct.** A
fresh checkout attains zero bands. Anyone surprised by this has the wrong model
of what the tool is for.

**A recurring assurance run becomes load-bearing rather than operational.** With
a 24-hour default window, every band closes a day after its last attestation.
The schedule is part of the system, not part of the ops around it.

`tests/test_failclosed.py` exists to assert this directly: faults become
denials, never implicit allows. A positive-control test suite sits beside it,
because a gate that denied unconditionally would pass every other assertion in
the repository.

## Reversal

None by exception. If the denial rate makes the tool unusable, the answer is
per-control windows tuned to what can actually be proven, or fewer wired
controls honestly declared — never a neutral reading of absence.
