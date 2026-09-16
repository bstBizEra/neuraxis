# Architecture decision records

Nine decisions shape everything in this package. Until now they were true of
the code and written down in three different places — a README section called
"design decisions worth knowing", a roadmap retrospective, and a project doc
that only some readers have. That is the same failure this package exists to
prevent, one layer up: **a rule with no single place it lives is a rule that
gets re-litigated**, usually by someone reasonable, usually under schedule
pressure, usually correctly-arguing from the part of it they found.

So the rule here is the rule everywhere else in this repository. A decision
with no ADR does not exist: it is a preference, and preferences lose.

| # | Decision | Status |
|---|---|---|
| [0001](0001-bands-not-levels.md) | Bands, not levels, are the unit of attainment | Accepted |
| [0002](0002-missing-attestation-denies.md) | A missing attestation denies, and there is no partial registry | Accepted |
| [0003](0003-two-principal-folds.md) | Two principal comparisons with opposite folding rules | Accepted |
| [0004](0004-one-implementation-of-the-gate.md) | One implementation of the gate; clients hold no rules | Accepted |
| [0005](0005-sources-are-black-boxes.md) | An attestation source is a black box, proven before it is trusted | Accepted |
| [0006](0006-floors-are-constants.md) | Non-compensable floors are constants in code, not registry settings | Accepted |
| [0007](0007-l0-shells-out.md) | L0 reaches the gate by shelling out to the CLI | Accepted |
| [0008](0008-roadmap-is-a-graph.md) | The roadmap is a dependency graph resolved against the live gate | Accepted |
| [0009](0009-a-ruling-names-its-enforcement.md) | A ruling names the code that enforces it | Accepted |

## How these relate to ILR-001-DR

The decision register (ILR-001-DR) rules on the **framework**: what the bands
mean, where IL-13 sits, what the formula is for. These ADRs rule on the
**artefact** that enforces it. Several implement a register ruling and say so;
0003, 0004 and 0005 have no register counterpart at all, because they are
questions the register never had to face.

Where an ADR implements a ruling, the ruling is normative and the ADR records
how it was drawn. Where they would conflict, the register wins and the ADR is
the bug.

## Writing one

Short. Context, the decision, what it costs, and what would reverse it.

**The reversal condition is the part that matters.** A decision with no stated
way to be wrong is not a decision, it is a belief — and the register makes the
same demand of its own rulings for the same reason.
