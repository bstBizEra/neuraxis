# 0006 — Non-compensable floors are constants in code, not registry settings

**Status:** Accepted · **Date:** 2026-09-13 · **Implements:** ILR-001-DR D-05, D-06

## Context

ILR-001-DR D-06 declares GV-01, GV-02, GV-03 and GV-08 non-compensable: no
waiver path, no named-accountable path, no expiry path. Integrity controls
cannot be compensated by human process, because an append-only evidence sink a
human promises not to rewrite is a rewritable evidence sink, and external
attestation performed by an internal party is not external attestation.

The first implementation put the floor in the registry YAML, next to everything
else configurable. An adversarial review found that four line deletions removed
it, with no error and no failing test. The rule was true in the document and
absent from the code.

D-05's waiver bounds had the same shape: a TTL ceiling, an active-waiver cap
and a renewal limit, all of them settings a registry could widen.

## Decision

**A bound that exists to constrain the registry cannot live in the registry.**

```python
NON_COMPENSABLE_FLOOR = frozenset({"GV-01", "GV-02", "GV-03", "GV-08"})
MAX_TTL_CEILING       = timedelta(days=90)
MAX_ACTIVE_CEILING    = 2
MAX_RENEWALS_CEILING  = 1
```

The registry may **tighten** and never loosen. `WaiverPolicy.__post_init__`
unions the floor with whatever the registry declares and clamps every ceiling
with `min(...)`, so a registry asking for a 365-day TTL gets 90.

The same rule governs D-07's blocking-event list and the envelope magnitude
ceiling.

## Consequences

Changing a floor is a code change, which means a pull request, a review and a
release — which is the intended cost. The registry stays the place where a
programme describes itself, and stops being the place where it can quietly
describe away a constraint.

`registry._assert_envelope_floor` extends the principle to agreement between
fields: `authority.envelope_required` must match `envelope_bounded`, or the
registry does not load. Otherwise deleting one YAML token turns IL-13a into
unbounded self-tuning with no error and no failing test — the original bug,
one field over.

## Reversal

None by exception for D-06's four controls. The register forecloses it: the
floor reopens only if KBS-001's scope changes so that T1 no longer implements
all four, in which case the matrix is re-derived, not waived.
