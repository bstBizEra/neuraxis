# 0008 — The roadmap is a dependency graph resolved against the live gate

**Status:** Accepted · **Date:** 2026-09-16

## Context

Every rule in this repository is mechanical. The plan that decides what to build
next was prose.

That asymmetry is not cosmetic. The roadmap carried the phrase "blocked on T1"
in eleven places, and a phrase is something an agent has to interpret.
Interpretation under schedule pressure is how "blocked on T1" becomes "we will
do T1 after". A status column saying `shipped` is a claim nothing checks; an
external dependency written as a string is a blocker nobody owns; and an item's
readiness was whatever the last person to edit the file believed.

This is the same error [0001](0001-bands-not-levels.md) corrected in the
capability index, occurring in the plan instead of the system.

## Decision

`src/neuraxis/config/roadmap.yaml` is the normative build sequence; `ROADMAP.md`
is its narrative companion. `neuraxis roadmap` answers *what is actionable now*.

Three properties carry the weight:

**Readiness is computed, not declared.** `state` is a claim a human typed.
Readiness comes from the same resolver the gate runs on — band attainment from
the registry and attestation store, control freshness from the same windows,
item dependencies from the file itself.

**A gate unsatisfied under a `shipped` state is a CONTRADICTION**, reported as
one rather than as green. Acceptance commands run for anything claiming to have
shipped, so `state: shipped` and a failing acceptance is caught too.

**An unevaluable gate blocks.** An unrecognised gate kind, a band not in the
registry, a command gate that was not run: all UNKNOWN, never READY. This is
[0004](0004-one-implementation-of-the-gate.md)'s unrecognised-exit-code rule,
applied to the plan.

Two refusals at load make the graph a graph: a gate naming an item or external
that does not exist is a load failure, not a permanent mystery blocker; and an
external with no owner is refused, because an external nobody owns is a wish.

## Consequences

**The roadmap is not kernel.** Nothing in it licenses a capability, opens a band
or waives a control, so changing it is a plan change and `neuraxis drift` does
not cover it. The moment a roadmap could grant something it would have to be
kernel, and the fact that it cannot is what keeps it cheap to edit.

A test asserts the shipped roadmap contradicts itself nowhere, so marking an
item shipped while its gates are unsatisfied fails CI.

The cost is that the plan now has invariants, and a plan with invariants is
slower to change. A roadmap entry is thirty seconds of YAML rather than a line
of prose, and it must name an owner.

## Reversal

Items accumulate that cannot be expressed as gates, and the YAML becomes a
second place to write prose. The fix then is a richer gate kind, not a return
to a status column.
