---
name: evidence-assessment
description: Decide whether a claim is actually supported — establish jurisdiction, classify the evidence E0–E5, weigh it, and resolve conflicts without averaging them. Use before asserting that something works, is secure, is authorised, or is done.
---

# Weighing evidence

Two questions, in this order. The order is the whole discipline: a very strong
source for the wrong kind of claim is still the wrong source.

## 1. Jurisdiction — which source may decide this?

| Kind of claim | Has jurisdiction | Here |
|---|---|---|
| Authority | governance contract, operator | kernel, `neuraxis register`, roadmap externals |
| Architecture | accepted ADR | `docs/adr/` |
| Requirement | authorised work item | `roadmap.yaml`, the ILR-001 spec |
| Implementation | the source, at HEAD | `src/`, `git log` |
| Runtime behaviour | a reproducible probe | the test suite, CI, `neuraxis` runs |
| Vendor capability | current official docs | Claude Code docs, GitHub API docs |
| Security | a probe that fails when the property is broken | `tests/test_failclosed.py`, vacuity probes |

The rules that follow from this, and that get broken most often:

- **A runtime observation cannot grant authority.** That the drill runner works
  does not mean GV-05 is attested; attestation needs a second principal.
- **A document cannot prove code works.** `docs/ROADMAP.md` saying an item
  shipped is E1.
- **An agent summary never overrides an ADR** — including a summary written
  minutes ago by the agent reading it now.

## 2. Class, then weight

```
E5  direct executable evidence   a run, now, reproducible
E4  current verified engineering CI result, contract test, security probe
E3  authoritative project contract  ADR, governance record, roadmap item
E2  authoritative external source   official vendor docs, a standard
E1  derived                         PR body, issue comment, report
E0  informal                        recollection, assumption, chat summary
```

Within the right jurisdiction:

```
weight = 0.25·authority + 0.20·directness + 0.15·reproducibility
       + 0.15·freshness + 0.15·independence + 0.10·completeness
```

each dimension in {0, 0.25, 0.50, 0.75, 1.00}.

Do not manufacture precision. The number exists so two options can be compared
the same way twice; quoting it to four decimals implies a measurement that was
not taken. **Independence** is the dimension that silently collapses here: a
test I wrote, run by me, against code I wrote, scores low on independence no
matter how green it is. That is not pedantry — it is NX-INV-2 applied to my own
claims.

## The vacuity question

Before accepting any passing check as evidence, answer: **what would make this
fail?** If there is no such input, the check is vacuous and its pass is worth
E0 regardless of where it ran. This repository takes that seriously enough to
put a vacuity probe in every provider (`providers/harness.py`) and to run the
assist classifier's positive control in CI. Apply the same test to a new check
before citing it.

The failure arrives from the cautious side more often than the permissive one,
and that side is the one nobody inspects: a classifier that refuses everything
reports a clean repository every day and looks correct doing it.

## Conflict

```
CONFLICT → jurisdiction → freshness → directness → reproduce
         → verify independently → resolve, or mark UNRESOLVED
```

Never average contradictory claims into a middle number. If a contract and an
observation disagree:

```
SPEC:           X
IMPLEMENTATION: Y
VERDICT:        NON-CONFORMANT
```

and leave the contract alone. Rewriting the spec to match the software is how a
governance framework becomes a description of whatever was built.

## Recording it

For a claim that matters:

```yaml
claim:
jurisdiction:
source:
evidence_class:
weight:
what_would_falsify_this:
unresolved:
```

`what_would_falsify_this` is not decoration. A claim with no falsifier is not a
finding, it is an impression.
