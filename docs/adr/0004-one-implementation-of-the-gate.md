# 0004 — One implementation of the gate; clients hold no rules

**Status:** Accepted · **Date:** 2026-09-11

## Context

The gate is consumed from Python, from Node (maw-js), from CI, and will be
consumed by L0. The obvious way to serve four callers is to give each one a
client that understands the rules.

Two implementations of a governance decision are two governance decisions. They
agree on the day they are written and diverge from the first change onward, and
the divergence is invisible: each side passes its own tests.

The specific way it goes wrong is exit codes. A client that hard-codes
`{ALLOW: 0, DENY: 10, ESCALATE: 11}` is correct until a `Decision` is added on
the gate side. Then the new code arrives at the client as a number that maps to
nothing — and in a governance client, "maps to nothing" means "not recognised as
a block".

## Decision

**The gate logic exists once, in Python.** Every other client is a transport.

The contract between them is `neuraxis contract`, which emits the decision and
exit-code table, the permitting decision, obligations, risks, accepted request
fields, and the caller requirements. **Clients assert against it rather than
holding a copy.** The Node client's table is checked against it in CI, so
adding a `Decision` in Python fails the JS tests instead of silently widening
authority.

Three rules follow, and every client implements all three:

- Only `ALLOW` permits. Everything else blocks, including a decision the client
  has never heard of.
- An unrecognised exit code or decision throws. Never a pass.
- Exit code and decision field must agree; when they disagree, no verdict from
  that run is trustworthy.

## Consequences

The CLI's JSON output is a public contract and its human output is not. Changing
the JSON shape is a breaking change.

The README's standing warning — *callers must test for zero, not for a code
list* — is now three failing scenarios in `neuraxis caller-conform` rather than
a sentence. See [0007](0007-l0-shells-out.md).

A client cannot be faster than a process boundary allows. That is acceptable
because the gate is consulted at authority grant, not per action (ILR-001-DR
D-03), so grants are rare.

## Reversal

A caller needs a decision this gate cannot make in a subprocess round trip —
per-action gating at high frequency, say. That is a request to revisit D-03,
not this ADR.
