# 0010 — A record does not grant itself: two locks on unattended work

**Status:** Accepted · **Date:** 2026-09-21 · **Implements:** ILR-001 section 6.4, D-03; enforces AGENTS.md (biztrust_guide) sections 3, 5, 11

## Context

The BizTrust Docs Hub (`bstBizEra/biztrust_guide`) is run by agents under a
written charter. Its operational state is two JSON files, `badf/current-state.json`
and `badf/next-actions.json`, and each pending action carries an `authority`
string, an `owner_role`, an evidence requirement and a list of stop conditions.
The stop conditions are the real control. Three of them, verbatim:

> An agent posts the waiver, or a chat instruction is treated as the waiver (DEC-043)
> An agent supplies either answer
> An agent occupies or infers a seat

They are correct, they are binding, and until now they were enforced by an
agent reading them carefully. That is a control made of care. It holds exactly
as long as nothing is urgent. The failure mode is not an agent deciding to
defy a stop condition; it is an agent deciding, reasonably and under pressure,
that *this* case is not what the condition meant — that the operator's chat
message was effectively the waiver, that the human would have said yes, that
recording the answer is not the same as supplying it. Every one of those is a
sentence a careful reader can write.

The second temptation is worse, because it looks like rigour: let the record
decide. The action says `authority: OPERATOR_INSTRUCTION_..._PROCEED_ON_YOUR_CALL`,
so proceed. But that is a line of JSON in another repository, editable by
anyone who can open a pull request there, and treating it as the thing that
opens a capability makes the hub's own file the gate.

## Decision

**An unattended agent may perform a recorded action only if the record grants
it and the gate allows it. Either lock alone refuses.**

`neuraxis assist` (module `neuraxis.biztrust`) computes the answer instead of
reading it. The record's half is five clauses, each a constant in code for
0006's reason — *a bound that exists to constrain a record cannot live in that
record*:

| Clause | Refuses when |
|---|---|
| authority | no grant phrase, or any reserving token (`HUMAN`, `NOT`, or a stem: `REQUIR`, `PEND`, `APPROV`, `RATIF`, …) |
| seat | `owner_role` maps to no role this registry grants; the mapping may not name a human seat, asserted at import |
| stop condition | any stop condition names an agent, automation or a bot |
| evidence | the required evidence is a person's to produce, or there is none |
| record | the two files disagree, priorities are not 1..n, the checkpoint is absent, `resume_decision` is not `CONTINUE`, or no revision can be observed |

The gate's half is an ordinary `AuthorityRequest` for IL-06 (BAND-B), which
means GV-01 through GV-05 must hold, a verifier independent of the performer
must be named (NX-INV-2) and a tested rollback must be asserted (NX-INV-3).
The hub's authority string cannot satisfy any of them.

**The module has no write path.** Git is restricted to a read-only allowlist in
code, so acquiring one would be a visible change rather than an argument. What
the run produces is a report. Automation may propose; merging stays GV-07's.

**The classifier proves itself live before every run.** `selftest()` runs a
positive control and a vacuity probe — the providers' rules 2 and 3, applied to
the thing that decides what an agent may do — and a run whose self-test is not
live reports DENY with nothing executable.

## Consequences

The expected answer on a healthy hub is exit 12, WAIT_FOR_AUTHORITY, and that
is a finished run rather than a failure. On the hub's record as of
2026-09-10, eight of nine recorded actions are reserved to a person and the
ninth does not reach the gate, because the hub's own `resume_decision` is
`WAIT_FOR_AUTHORITY`. The tool's first useful output is the confirmation that
there is nothing an unattended agent should be doing — which is precisely the
claim that was previously made by an agent about itself.

Under-matching is the accepted cost. Two real operator grants
(`..._PROCEED_PROPOSED_ONLY`, `..._CONTINUE_ON_THE_TRACK_AS_RECOMMENDED_...`)
match no grant phrase and are therefore reserved. The remedy is for the hub to
adopt a canonical grant phrase, not for this module to guess at new ones: every
phrase added here widens what an agent may do to another repository, and the
report names each string it could not read so the gap is visible rather than
inferred.

The self-test earned its place on its first run. The veto list initially
included the role nouns `OPERATOR`, `REVIEWER`, `BROKER` and `PRINCIPAL`, on
the reasoning that a human role named in an authority string means a human owns
it. That refused the hub's own real grant, because the operator is the *source*
of an operator instruction. A classifier that refuses everything passes every
deny-assertion anyone would write against it and licenses nothing — the vacuous
check arriving from the cautious side, which is the side nobody inspects. The
positive control caught it before any test did.

## Reversal

- A hub that publishes a machine-checkable authority record — signed, typed,
  bound to a revision — would make clause 1's string parsing unnecessary. The
  clause would then read the record's own grant rather than its prose, and this
  ADR would be amended rather than reversed.
- If the hub's charter ever placed an agent in a seat this mapping refuses, the
  mapping is not the place to fix it: the seat is recorded in `owner_role`, and
  changing what that role means is the hub's decision, not this package's.
