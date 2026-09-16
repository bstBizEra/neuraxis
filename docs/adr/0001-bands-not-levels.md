# 0001 — Bands, not levels, are the unit of attainment

**Status:** Accepted · **Date:** 2026-09-10 · **Implements:** ILR-001-DR D-02

## Context

ILR-001 numbers 33 intelligence levels, IL-01 to IL-33. A numbered list is read
as a ladder whatever the surrounding text says — that is what numbered lists
do — and a ladder instructs an implementer to proceed down it.

In the original numbering that instruction was actively dangerous. IL-13
Self-Improving sat eleven levels below IL-24 Self-Auditing and IL-27
Self-Explaining, so a team reading it as a progression would ship
self-improvement long before the system could audit itself or explain a
decision. The framework's own principle inverted by its own presentation.

"We are at level 22" is also not a certifiable claim. There is nothing to
attest against, so it degrades into a marketing number.

## Decision

The banded dependency graph is normative. **Bands A–G are the only unit the
gate resolves and the only unit that can be attested.** The flat IL index may
be published for orientation, marked non-normative, with its dependency edges
shown.

Ordinal attainment claims are prohibited in any contract, proposal, marketing
asset or regulatory filing. The permitted form is "Bands A and B attained;
Band C in progress", with the attestation reference.

Bands C, D and E are parallel. Nothing requires learning before coordination.

## Consequences

The registry asserts acyclicity, monotonicity and a single root at load. A band
resolves through its dependency closure, and the resolver reports the **root**
blocker rather than the nearest one — the nearest is rarely the one to fix.

Monotonicity is the invariant with teeth: each band's control set must be a
superset of every band below it. Without it some transition *reduces* required
controls, which is unauditable and creates an incentive to declare a higher
band to escape a control.

The cost is coarseness. A band is a large unit to certify, and a team that has
built four of a band's six capabilities attains nothing. That is the intended
trade: band granularity is coarse enough to certify, and per-capability
attestation multiplies the attestation surface by roughly the IL count.

## Reversal

An external party — client, auditor, partner — cites an ordinal level back in
writing. That means the index is being read as normative, and it gets pulled.
