# Working in this repository

`neuraxis` is the reference implementation of ILR-001: a fail-closed gate that
licenses capability bands by the governance-control attestations paired to
them. Everything here exists because **a control made of prose is enforced by
the care of the party it constrains, which is not enforcement.** That is the
standard this file is held to as well — it points at authority, it is not
authority. Nothing in `.claude/` may become the project's source of truth.

---

## Source precedence

When two sources disagree, the higher one wins and the disagreement gets
recorded rather than averaged away.

| Rank | Source | In this repository |
|---|---|---|
| 1 | Current executable evidence | `neuraxis status`, `neuraxis roadmap --check`, `pytest`, CI |
| 2 | Current governance state | `src/neuraxis/config/neuraxis.yaml` (KERNEL), the attestation ledger |
| 3 | Accepted architecture | `docs/adr/`, `neuraxis register` |
| 4 | Authorised work | `src/neuraxis/config/roadmap.yaml`, `docs/ROADMAP.md` |
| 5 | Proposals and notes | PR bodies, issues, this conversation |

A roadmap entry does not prove code works. A passing test does not grant
authority. An ADR outranks any summary of an ADR, including one I wrote.

If the contract and the behaviour disagree, record it as
`SPEC: X / IMPLEMENTATION: Y / VERDICT: NON-CONFORMANT` and stop. Do not
reinterpret the contract to match the software.

---

## Invariants that are not mine to relax

Each is enforced somewhere in code; the pointer is where to look before
arguing with it.

- **The gate fails closed.** Absence, expiry, future-dating, an unknown
  capability, a malformed registry and an internal exception all produce
  `DENY`. → `src/neuraxis/gate.py`, `tests/test_failclosed.py`
- **NX-INV-2 — the verifier is not the performer.** → `gate.py:_check_verifier_independence`, ADR-0003
- **NX-INV-3 — an untested rollback counts as no rollback.**
- **ADR-0006 — a bound that constrains X cannot live in X.** Floors are
  constants in code, not config. This is why the kernel is not writable from
  here, and why the guard in `.claude/hooks/` has no off switch.
- **ADR-0010 — a record does not grant itself.** Evidence is emitted by the
  tool that witnessed the event. It is never typed.
- **D-06 — GV-01 and GV-03 are non-compensable.** There is no waiver path.
  BAND-A does not open until T1 lands, and no amount of local work changes
  that.
- **Every provider obeys four rules**: fail closed, positive control, vacuity
  probe, cite evidence. → `src/neuraxis/providers/harness.py`. A new check
  that cannot fail is worse than no check, because it reports green.

---

## What an agent does not do here

Not preferences — these are the actions that would make the rest of the
repository decorative.

1. **Write the kernel** (`src/neuraxis/config/neuraxis.yaml`). Propose it.
2. **Author evidence** — `*-log.jsonl`, `attestations.jsonl`, the `verifier`
   field of a drill record. Run the tool that produces it, or leave it empty.
3. **Sign your own work.** If I performed it, I am not the verifier, and
   `scripts/rollback_drill.py` will refuse `--verify --as <performer>`.
4. **Issue a waiver, or widen one.** The exception path is recorded, expiring
   and human-issued.
5. **Occupy or infer a human seat** — operator, ratifier, approver, reviewer —
   in this repository or in `biztrust_guide`. Whether an unattended agent may
   act on a Docs Hub record is decided mechanically by `neuraxis assist`, not
   by reading the record carefully. → `docs/BIZTRUST-ASSIST.md`
6. **Cut a release or push a tag.** Ratification is the operator's.
7. **Skip, relax or quarantine a failing test** to get to green.

Items 1 and 2 are enforced by `.claude/hooks/kernel_guard.py` for `Write`,
`Edit` and the obvious shell shapes. The rest are enforced by nothing but this
file, which is exactly the weakness named at the top — treat them as the list
of controls most worth converting into mechanisms.

---

## State

This repository has its own vocabulary and it wins over any imported one.

- Roadmap items are `planned`, `in-progress`, `partial`, `shipped`, `blocked`,
  `deferred` (`ITEM_STATES` in `src/neuraxis/roadmap.py`). Only `shipped`
  satisfies a dependency.
- A gate is `READY` or `BLOCKED`, and an unrun command gate is `UNKNOWN`,
  which blocks.
- Bands are `ATTAINED` or `BLOCKED` against the live ledger.

Never promote a state by editing the YAML. A state changes when the thing it
describes changes, and `neuraxis roadmap --check` runs the gates that say so.

---

## Verifying a change

Before proposing anything:

```bash
python -m pytest -q                    # the suite, including the hook guard
neuraxis validate                      # registry integrity
neuraxis providers                     # coverage, including UNWIRED controls
neuraxis assist --self-test            # the classifier still discriminates
```

CI additionally proves the gate refuses everything with an empty ledger
(`.github/workflows/ci.yml`, job `gate-self-check`). If that job ever passes by
allowing, nothing else in the suite means anything.

For a new check, the bar is in `.claude/skills/verification/SKILL.md`: show the
test failing for the stated reason before you show it passing.

---

## Reporting

End substantive turns with what changed and what is still unproven — state,
evidence, blockers, and the one next action, in whatever form is clearest. The
part that is not optional is naming what remains **unverified**: this
repository's whole thesis is that an unexamined green is the dangerous kind.
