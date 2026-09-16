# 0009 — A ruling names the code that enforces it

**Status:** Accepted · **Date:** 2026-09-16 · **Implements:** ILR-001-DR W8

## Context

The decision register makes a demand of itself: *a ruling with no reversal
condition is dogma*, and *a ruling with no enforcement point is an opinion that
loses to schedule pressure*. Both were true of the document and unenforced by
anything.

Two failures follow, and neither announces itself.

**A ruling detaches from its implementation.** A document can describe an
enforcement point that was renamed three releases ago and read exactly as
convincingly as one that still exists. Nothing in a prose register notices;
nothing in a test suite notices either, because the tests exercise the code, not
the claim about the code.

**A reversal trigger becomes something remembered.** *"Any waiver renewed
twice"* is a condition a person has to check. Some triggers genuinely cannot be
watched by a machine — *an external party cites an ordinal level back to BST in
writing* arrives in an inbox, not in the evidence sink — but there was no way to
tell those apart from triggers nobody had got round to wiring.

## Decision

`src/neuraxis/config/register.yaml` carries the rulings, and two invariants make
it more than a YAML transcript of the document.

**Every ruling names the symbol that enforces it, and that symbol must import.**
`module:name` or `module:Class.name`, resolved at load. Rename
`NON_COMPENSABLE_FLOOR` and the register stops loading. A ruling may also name a
capability the shipped registry must carry — D-01 is enforced partly by IL-13a
and IL-13b existing at all.

**Every reversal trigger is either detectable or owned.** A detector is a
command with the exit code that means ARMED, or `by_construction` with a stated
reason the trigger cannot fire. A trigger without a detector must name an owner
*and* a review cadence. **A trigger that is neither fails to load**, because a
trigger that is neither is remembered, and a remembered trigger is one nobody
notices firing.

`neuraxis register --check` runs the detectors. **`NOT RUN` is reported as
distinct from `CLEAR`**, because they are different facts: one means nobody
looked.

## Consequences

Refactoring now has a new way to break the build, which is the point. Renaming
an enforcement point is exactly the moment to ask whether the ruling still
holds.

**A detector that cannot answer is ARMED, not clear.** An exit code that is
neither 0 nor the armed code means the detector faulted, and the trigger it
watches is unwatched — reading that as clear is [0004](0004-one-implementation-of-the-gate.md)'s
unrecognised-exit-code failure inside the thing that watches for failures.

The file is **not kernel**. Nothing in it bounds anything: the enforcement
clauses in the register document are descriptive, and the authoritative ones are
constants in code ([0006](0006-floors-are-constants.md)). Putting the
non-compensable floor in this YAML would re-create the exact bug that ADR fixed.

Detectors resolve `neuraxis` through `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS`, then
PATH, then this interpreter. A PATH miss is not evidence about the register, and
hard-coding the path would be [0007](0007-l0-shells-out.md)'s substitutability
problem occurring inside the thing that watches D-07.

## Reversal

The symbol references become churn — renamed constantly for reasons unrelated
to the rulings. The fix then is coarser references (a module rather than a
symbol), not dropping the check.
