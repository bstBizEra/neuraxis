---
name: project-discovery
description: Reconstruct where this project actually stands — bands, blockers, review dates, freeze state — from executable sources rather than recollection. Use at the start of a session, after a compaction, before proposing work, or whenever a claim about project state needs to be settled.
---

# Reconstructing project state

The failure this guards against is specific: an agent resumes, recalls that
"GV-05 is wired now", and plans on top of a memory. Memory is E0 evidence. This
repository publishes its state as E5 — commands that resolve against the live
gate — so there is never a reason to guess.

## The five commands

Run them. Do not summarise them from memory, including your own summary from
earlier in the same session.

```bash
neuraxis status            # band attainment against the current ledger
neuraxis roadmap           # every item, its gates, its blockers, review dates
neuraxis providers         # which controls have a real source, which are UNWIRED
neuraxis register          # the seven rulings, what enforces each, what reverses it
git log --oneline -10      # what actually shipped, versus what a doc claims
```

`neuraxis roadmap --check` additionally runs the command gates. It is slower
and it is the only version whose answer is complete: **a gate that was not run
is `UNKNOWN`, and `UNKNOWN` blocks.** A roadmap read without `--check` ends
with a NOTE saying how many gates were skipped. Do not report "nothing is
actionable" from a run that skipped six gates without saying so.

## What each source may be trusted for

| Question | Ask | Do not ask |
|---|---|---|
| Is this band open? | `neuraxis status` | the README's example output |
| Is this item actionable? | `neuraxis roadmap --check` | `state:` in roadmap.yaml |
| Does this code work? | the test suite | `docs/ROADMAP.md` |
| Why is this designed this way? | `docs/adr/` | a PR description |
| Who must decide this? | `neuraxis roadmap` review table, `neuraxis register` | inference |
| May an agent act on a Docs Hub record? | `neuraxis assist` | reading the record |

`state:` in `roadmap.yaml` is an assertion by whoever last edited it. The gates
are what resolve. When they disagree, the gate wins and the disagreement is a
finding.

## What to establish before proposing work

- **What is complete** — shipped items, and whether their acceptance checks ran.
- **What is verified** — distinct from complete. A shipped item whose gate was
  `UNKNOWN` is complete and unverified.
- **What is blocked, and on whom.** Externals carry an owner and a `review`
  date; `neuraxis roadmap` prints them sorted. An external with no owner is
  itself a finding.
- **What is frozen.** ILR-001-DR-3.3 freezes some work regardless of gates, and
  the roadmap prints what lifts it.
- **Which decisions are outstanding.** T1 carries dated `decisions`; those are
  the largest blocker in the project and they are waiting on a human, not on
  code.

## The trap

Most of this roadmap is blocked on externals owned by OP-Vily, and the honest
answer to "what is actionable?" is frequently "nothing that opens a band."
Resist converting that into local work that looks like progress. Work that
cannot move a gate should be proposed as exactly that, and the blocker should
be named with its owner and its review date.
