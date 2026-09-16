# 0005 — An attestation source is a black box, proven before it is trusted

**Status:** Accepted · **Date:** 2026-09-15

## Context

Four provider rules have been enforced since v0.3 — fail closed, positive
control, no vacuous probe, emit an evidence reference — by a harness that only
providers living in this repository pass through.

The controls that matter most will not live here. GV-01, GV-03 and GV-08 are
attested by the external assurance account, GV-02 and GV-06 by L0, GV-07 by
BADF. Until v0.11.0 none of them had any way to show a source conformed before
it was trusted, which is how a programme ends up having trusted an attestation
source nobody tested.

The failure is specific and quiet: a check that was correct when written, has
since stopped exercising anything, and still reports green.

## Decision

A source is an **executable**: one JSON object in on stdin, one JSON attestation
out on stdout. `neuraxis conform` drives it through four scenarios and applies
the rules to what comes back.

| Scenario | The source should | Rule |
|---|---|---|
| `live` | run normally | emit a real evidence reference, not `"pass"` |
| `broken` | run with a dependency unavailable | never report PASS |
| `negative` | run against a condition it must reject | report FAIL — a source that cannot fail is not a check |
| `powerless` | run as an identity with no authority | not pass |

**The kind comes from the registry, not the source.** `powerless` is required
only for a control declared `kind: probe`, and a source that could declare its
own kind could declare its way out of the vacuity check. The field defaults to
`probe`, so omitting it tightens.

`examples/vacuous_source.py` ships deliberately. A conformance suite nobody has
seen fail is itself an unverified check.

## Consequences

Black box is the point: the assurance account should not have to write Python
to show its probe is honest.

**What conformance does not prove.** Every scenario is implemented by the
source, which decides for itself what "broken" and "negative" mean. Passing
shows a source *can* fail and *does* carry evidence — not that it fails when it
should. It raises the floor. The thing that would make it a proof of honesty is
the same as everywhere else here: KBS-001 T1.

## Reversal

A source is found conforming and dishonest. The answer is T1 — signed
attestations from an authenticated identity — not more scenarios.
