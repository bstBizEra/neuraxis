# 0007 — L0 reaches the gate by shelling out to the CLI

**Status:** Accepted · **Date:** 2026-09-16 · **Implements:** ILR-001-DR D-07

## Context

ILR-001-DR §3.3 freezes new authority grants until W9 and W2 are live. Both are
specified *at lease issuance*. This package is the grant-time gate and can deny
a request perfectly — but it does not issue leases, so until something at lease
issuance calls it, neither item is live and the freeze does not lift.

Four shapes were scored: an in-process import, a long-running HTTP service, a
generated static policy file evaluated by L0, and shelling out to the CLI.

## Decision

**L0 invokes `neuraxis gate` at each of D-03's five blocking events and refuses
the grant on any non-zero exit.** The full ruling, with scores, is the register
addendum; the integration contract is `docs/L0-LEASE-GATE-CONTRACT.md`.

The generated-policy-file option is foreclosed explicitly, because it is the one
proposed when someone measures process-spawn latency. It is a copy of the gate's
decisions living on the far side of the boundary, and it goes stale silently —
[0004](0004-one-implementation-of-the-gate.md)'s failure at a larger scale.

The service option fails differently: it puts an availability dependency on the
thing that grants authority, and a team whose grants have stalled builds an
emergency bypass that becomes the normal path within a quarter.

## Consequences

**The entire enforcement burden crosses a process boundary.** Four ways a caller
looks correct and licenses everything: blocking on exit 10 and treating 11 as
success; treating a CLI fault as no objection; treating an unrecognised exit
code as permission; and dropping `verifier` in transit, which fails nothing and
switches off W9 entirely.

So the decision is Option D **plus** `neuraxis caller-conform`, not Option D
alone. Without a suite that fails when a caller gets it wrong, shelling out
scores worst on blast radius rather than best, and the ruling inverts.

The gate is resolved from `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS` so a scripted
gate can be substituted. A caller that hard-codes the path cannot be tested,
and an untestable caller is an unproven one.

## Reversal

Any of: a grant path found in production that did not call the gate; a gate
verdict cached or reused across grants; or `caller-conform` absent from L0's CI
for two consecutive releases. Each means the boundary is being worked around
rather than crossed. Fallback is the service option with a mandatory
fail-closed client, accepting the availability cost this decision avoided.
