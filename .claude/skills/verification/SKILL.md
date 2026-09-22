---
name: verification
description: Prove a change in this repository actually holds — show the test failing for the stated reason before showing it pass, check the new check is not vacuous, and run the suite the way CI does. Use before proposing, committing or claiming anything is done.
---

# Verifying a change here

A green suite is the weakest kind of evidence about a check that has never been
observed to fail. Everything below exists to distinguish "this passes" from
"this would catch the thing it claims to catch".

## The bar for a new check

1. **Make it fail first, for the stated reason.** Break the input the check is
   about, run it, read the message. If the failure message does not name the
   defect, the check will not be understood at 3am.
2. **Then make it pass**, by fixing the thing — not by adjusting the assertion.
3. **Probe it for vacuity.** Mutate the implementation so the property is
   genuinely violated and confirm the check goes red. A check that survives the
   mutation is testing the wiring, not the property.
4. **Positive control.** Confirm it still *accepts* the legitimate case. A
   check that refuses everything reports a clean repository every day. This
   failure arrives from the cautious side, which is the side nobody inspects.

Steps 3 and 4 are the four-rule provider contract (`providers/harness.py`)
applied to ordinary tests, and to hooks: `tests/test_claude_hooks.py` runs two
mutants of `kernel_guard.py` past its own suite for exactly this reason.

## The commands

```bash
python -m pytest -q                                   # full suite
python -m pytest -q --cov=neuraxis --cov-report=term-missing   # as CI runs it
neuraxis validate                                     # registry integrity
neuraxis providers                                    # control coverage
neuraxis assist --self-test                           # classifier discriminates
```

Coverage has `fail_under = 90`. That is a floor against untested code arriving
silently, not a target to satisfy — coverage measures that a line ran, never
that a property holds.

## Things this repository has been bitten by

Check these specifically; each was a real defect, and all of them failed
*closed*, which is the hardest kind to notice.

- **Encoding.** Readers use `utf-8-sig`. A PowerShell-written file starts with
  a BOM, and a BOM on line 1 makes the whole file unreadable — a denial for an
  encoding reason dressed as a governance one.
- **Windows.** CI runs the suite on `windows-latest` for the BOM case and for
  em-dashes against a legacy console code page. Both are in the matrix; do not
  assume POSIX.
- **Substring versus word.** `"signed"` matched inside `"designed"`. Token and
  boundary matching, not `in`.
- **Inflection.** A veto list of exact words let `..._WHEN_APPROVED` through.
  Stems where the family matters.
- **Timestamps.** Naive datetimes are a breach, not something to coerce;
  ordering across absent offsets is not decidable.
- **Present-but-falsy.** `""` and `0` skipped an ordering check entirely while
  `"garbage"` was caught. Distinguish absent from empty.

## Before proposing

- Full suite green, on the change as it stands.
- The new check observed failing at least once, for the right reason.
- Re-read the diff adversarially: what input makes this wrong?
- If a pinned inventory test changed, say so explicitly and say why the new
  inventory is correct. Updating a pinned test quietly is how a pin stops
  pinning.
- Name what is still **unverified**. Something always is.

## What verification is not

Running the drill is not attesting it. `scripts/rollback_drill.py` leaves
`verifier` empty and has no flag to fill it, because the performer is not the
verifier (NX-INV-2) — a drill log I both produced and signed is a
true-looking lie one field wide. The same applies to my own claim that a change
works: I can show the evidence, and someone else scores independence.
