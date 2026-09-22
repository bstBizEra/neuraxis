# BizTrust assist — the contract

`neuraxis assist` answers one question about the BizTrust Docs Hub
(`bstBizEra/biztrust_guide`), unattended, on a schedule, with nobody present:

> **Which of the recorded next actions is an unattended agent's to perform?**

It answers by refusing, and it refuses twice. See
[ADR-0010](adr/0010-a-record-does-not-grant-itself.md) for why.

```bash
neuraxis assist --hub ../biztrust_guide --verifier github-ci --rollback-tested
neuraxis assist --self-test          # is the classifier live at all?
neuraxis --json assist --hub ../biztrust_guide --verifier github-ci
```

## What it reads

| Path | What it is used for |
|---|---|
| `badf/current-state.json` | active work package, `resume_decision`, `primary_next_action_id`, `latest_checkpoint`, `source.baseline_commit` |
| `badf/next-actions.json` | the ordered actions, each with `authority`, `owner_role`, `evidence_required`, `stop_conditions` |
| the checkout's git HEAD | the revision every conclusion is bound to (AGENTS.md section 9) |

It reads nothing else and writes nothing at all. Git is restricted to
`rev-parse`, `status`, `log`, `merge-base` and `symbolic-ref` by an allowlist
in code; anything else raises rather than runs.

## Exit codes

The gate's codes, unchanged. Every non-zero blocks.

| Code | Decision | Means |
|---|---|---|
| 0 | ALLOW | at least one action passed both locks. It may be **proposed**; merging is still GV-07's |
| 10 | DENY | the record would grant an action and the gate refused it |
| 11 | ESCALATE | the record is unreadable or disagrees with itself; a person repairs it |
| 12 | WAIT_FOR_AUTHORITY | every recorded action is a person's, or the hub's own resume decision says stop |
| 2 | error | the registry or attestation store could not be loaded |

**12 is the expected answer on a healthy hub** and is a finished run, not a
failure. A scheduled job should treat 11 as the one that wants attention.

## The five record clauses

An action must clear all five. Each is a constant in `neuraxis/biztrust.py`,
not a setting, because a bound that exists to constrain a record cannot live in
that record.

1. **Authority.** `authority` must contain a grant phrase — `PROCEED ON YOUR
   CALL`, `AGENT EXECUTABLE`, `GRANTED TO AGENT` — as consecutive whole tokens,
   and no reserving token. Reserving tokens are exact (`NOT`, `NO`, `NEVER`,
   `HUMAN`, `TBD`, `HOLD`, `SIGNED`) or stems (`REQUIR`, `WAIT`, `PEND`,
   `BLOCK`, `DEFER`, `EXPIR`, `LAPS`, `REVOK`, `WITHDRAW`, `SUSPEND`, `RATIF`,
   `APPROV`, `ESCALAT`). The veto is applied after the grant, so
   `PROCEED_ON_YOUR_CALL_ONCE_APPROVED` is reserved: a grant conditional on
   something that has not happened is not a grant.

   Separators do not matter — `proceed on your call`, `PROCEED-ON-YOUR-CALL`
   and `..._PROCEED_ON_YOUR_CALL_...` are one string to this clause.

2. **Seat.** `owner_role` must map through `HUB_ROLE_TO_NEURAXIS` onto a role
   this registry grants. Today: `documentation-engineer`, `continuity-engineer`
   and `validation-engineer`, all onto `drafter`. An unmapped role gets no
   neuraxis role and never reaches the gate. The mapping may not name a human
   seat — that is asserted at import, so adding `"human-reviewer": "operator"`
   fails to import. A caller may pass a **narrower** mapping and cannot widen
   one: an entry that is not already present, or that renames the role it maps
   onto, is dropped.

3. **Stop conditions.** Any stop condition naming an agent, automation, a bot
   or a model reserves the action. Matched on whole words, deliberately broad:
   a false positive costs an action not taken, a false negative is an agent
   doing the thing the record forbids.

4. **Evidence.** Evidence a person must produce — *"a comment with no agent
   marker"*, *"a written answer per tenant"*, *"one row per seat"* — reserves
   the action, because an agent that cannot produce the evidence cannot
   complete the action, only appear to. An action requiring **no** evidence is
   also reserved: work whose completion nothing would evidence is not
   unattended work.

5. **The record.** One work package across both files; exactly one primary
   action and `current-state` names it; priorities 1..n with no gap or repeat;
   no duplicate ids; the recorded checkpoint present in the checkout;
   `resume_decision` inside its own alphabet and equal to `CONTINUE`; a 40-char
   `baseline_commit` if one is recorded; an observable HEAD. **A fault here
   poisons the whole run** — every action reports REFUSED, because a record
   that disagrees with itself is not a record some of which can be trusted.

## The second lock

Every action surviving the five clauses is put to `GovernanceGate` as an
authority request for **IL-06 (Actionable, BAND-B)**. BAND-B requires GV-01,
GV-02, GV-03, GV-04 and GV-05, so in practice:

- nothing attested → every action DENIED, whatever the record says;
- `--verifier` unset → denied on NX-INV-2, *verification reliability is zero
  when unspecified*;
- `--verifier` equal to `--identity` → denied on NX-INV-2;
- `--rollback-tested` unset → denied on NX-INV-3, *untested rollback counts as
  none*.

Those defaults are the point. An assist run configured by nobody is refused by
the invariants rather than permitted by them.

## The self-test

`selftest()` runs before every pass and is reported in the JSON payload:

- **positive control** — an action drafted to be agent-executable must classify
  as executable. A classifier that refuses everything satisfies every
  deny-assertion ever written against it and licenses nothing.
- **vacuity probe** — an action reserved to a person in every clause must not.

A run whose self-test is not live returns DENY with an empty executable list.
`neuraxis assist --self-test` reports just this, exit 0 or 2, and is worth a CI
step of its own: it is the check that the check is a check.

## Reading the JSON

```jsonc
{
  "decision": "WAIT_FOR_AUTHORITY",
  "executable": [],                       // action ids that passed BOTH locks
  "triage": [
    {
      "action_id": "NS-041",
      "verdict": "HUMAN_ONLY",            // AGENT_EXECUTABLE | HUMAN_ONLY | REFUSED
      "clause": "authority",              // which clause decided it
      "reasons": ["authority 'HUMAN_DECISION_REQUIRED' carries the reserving token(s) HUMAN, REQUIRED"],
      "gate": null                        // null when the gate was never asked
    }
  ],
  "faults": [],                           // clause 5; non-empty means nothing is executable
  "selftest": {"live": true, "positive_control": true, "vacuity_probe": true},
  "observed": {"reachable": true, "head": "32ab2855…", "dirty": false},
  "state": {"work_package_id": "BIZTRUST-GUIDE-WP-118", "resume_decision": "WAIT_FOR_AUTHORITY"}
}
```

`executable` is the only field a caller should act on, and it requires the
gate's ALLOW: a triage entry can read `AGENT_EXECUTABLE` from the record's half
alone and still not appear there.

## Known limits

- **Clause 1 parses prose.** The hub's `authority` field is a free string, so
  this clause under-matches by design and the report names every string it
  could not read. Two real operator grants are currently reserved for that
  reason. The fix belongs in the hub — a canonical grant phrase — because every
  phrase added here widens what an agent may do to another repository.
- **Nothing is verified about the work itself.** This decides *whether* an
  action is an agent's, not whether the agent did it correctly. That is the
  gate's obligation set and the hub's own validator.
- **The verdict is not written anywhere.** Like every other verdict in this
  package, no later provider cycle can observe that an assist run happened, so
  an undischarged obligation from one is undetectable. See the README's known
  limits.
- **The hub's `resume_decision` is trusted as recorded.** If it says
  `CONTINUE` while the repository is in fact mid-recovery, this tool will
  believe it. The hub's own `scripts/validate_continuity.py` reconciles that
  and is the right place for it.
