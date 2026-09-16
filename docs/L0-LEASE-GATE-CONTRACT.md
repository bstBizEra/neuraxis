# ILR-001-DR D-07 — L0 ↔ gate integration contract

**Ruling:** L0 does not embed the gate. At each of D-03's blocking events it invokes `neuraxis gate` and refuses the grant on any non-zero exit.
**Depends on:** ILR-001-DR D-03 (synchronous at authority-grant), D-04 (verifier independence as a precondition), W9, W2.
**Conformance:** `neuraxis caller-conform -- <caller argv>`
**Machine-readable:** the `caller` block of `neuraxis contract --json`.

> **A note on numbering.** ILR-001-DR runs D-01…D-06; this is D-07 in that register. KBS-001 has its own D-nn sequence — KBS-001 D-06 is the second-code-owner ruling, D-08 is repository visibility — and the two are unrelated. Cite the register with the number.

---

## 1. The ruling, and what it moves

Four shapes were considered for the interface between L0 and the gate: an in-process Python import, a long-running HTTP service, a generated static policy file, and shelling out to the CLI. The CLI won for a reason that is worth keeping visible, because it is also the reason this document is longer than it looks like it needs to be:

**it is the only option that requires no new gate code, and therefore the only one where the freeze lifts on work L0 does rather than work this package does.** The CLI contract already exists. The Node client already wraps it. `neuraxis contract` already publishes the decision table, so nothing on the L0 side has to hold a copy.

That is the whole benefit, and it is real. The cost is that **the entire enforcement burden crosses a process boundary.** Neuraxis can return DENY perfectly and license nothing, because the thing that issues the lease is somewhere else, written by someone else, on the far side of an exit code. Every ruling in the register that this integration is supposed to make live — W9's verifier independence, W2's deny-on-missing-attestation — is now only as good as forty lines of process handling in L0.

So the deliverable from this side is not code. It is this contract, plus a suite that fails when a caller gets it wrong.

---

## 2. Where the gate is called

D-03's enforcement clause names five events. Each is a **separate call site**, and a caller proven correct at one says nothing about the other four:

```yaml
synchronous_blocking_on:
  [lease_issue, lease_widen, band_transition, envelope_amend, verifier_assign]
```

`neuraxis contract --json` publishes the same list under `caller.blocking_events`, so L0 can assert it covers all five rather than remembering that it does. The list is a constant in code for the same reason `NON_COMPENSABLE_FLOOR` is: a list that can be edited in config is a list that can be shortened under schedule pressure.

**`lease_widen` is the one that gets missed.** A widening is a fresh grant of authority the gate has never seen, and it arrives through a code path that already holds a valid lease — which is exactly why it feels like it does not need asking. D-03's reversal trigger (median lease TTL drifting upward) is the symptom of the team working around this one.

Actions *inside* an already-granted lease do not call the gate. That is D-03's split and it is what keeps throughput intact.

---

## 3. The invocation

```
$NEURAXIS_BIN $NEURAXIS_BIN_ARGS --json gate -
```

with one JSON object on stdin and the verdict on stdout.

**Resolve the binary from the environment, never hard-code it.**

| Variable | Meaning | Default |
|---|---|---|
| `NEURAXIS_BIN` | Path to the executable | `neuraxis` |
| `NEURAXIS_BIN_ARGS` | JSON array of leading arguments, e.g. `["-m","neuraxis"]` | `[]` |

This is the same `{bin, binArgs}` split the Node client already exposes, and it exists so the conformance suite can substitute a scripted gate. A caller that hard-codes the path cannot be tested, and an untestable caller is an unproven one — which in a governance chain is the same as an unenforced one.

Three properties of the invocation are not optional:

- **Arguments as argv, never a shell string.** `shell=False`, a list of arguments. A value inside a request must not be able to become a command. The CLI applies the same rule to itself: `neuraxis conform` refuses a command line rather than splitting one, because `shlex` eats the backslashes out of a Windows path and reports a source as *missing* when it is *failing*.
- **A hard timeout.** Set one, and treat its expiry as refusal. A gate that did not answer has not consented.
- **`--json`.** The human output is not a contract and will change.

---

## 4. The request

Field names are `AuthorityRequest`'s, published under `contract.request_fields`:

```json
{
  "intent":      "issue a write lease over the pipeline definitions",
  "identity":    "agent-motor",
  "role":        "motor",
  "capability":  "IL-06",
  "scope":       "bst-sa/pipelines",
  "risk":        "HIGH",
  "verifier":    "ci-runner",
  "performer":   null,
  "rollback_tested": true,
  "ratification_ref": "github://bstBizEra/secb_pf/pull/412",
  "envelope_ref": "ENV-MOTOR",
  "adjustments": {"retries": 5}
}
```

| Field | Required | What L0 puts in it |
|---|---|---|
| `intent` | yes | Why the grant is being requested, in a sentence |
| `identity` | yes | The principal the lease would be issued to |
| `role` | yes | Its declared role |
| `capability` | yes | `IL-nn` — the capability the lease exercises |
| `scope` | yes | The grant's scope. One string; for a multi-scope lease, one call per scope |
| `risk` | no | `LOW` \| `MEDIUM` \| `HIGH` \| `CRITICAL`. Defaults to `LOW` |
| `performer` | no | Set when the lease authorises one principal to act for another. Omit it rather than sending a blank — a blank switches off the obligation audit's self-discharge check, and the CLI rejects one |
| `verifier` | no | Who will verify the work. **See below** |
| `rollback_tested` | no | A JSON boolean. `"false"` is a non-empty string and the CLI refuses it: a truthy string is not a tested rollback |
| `ratification_ref` | no | The human authorisation, where the capability requires one |
| `envelope_ref` | no | For an envelope-bounded capability (IL-13a), the declared bound this request claims to sit inside |
| `adjustments` | no | What the request proposes to change, as `{name: number}`. Booleans are refused — an envelope bounds magnitudes, not flags |

Unknown fields are rejected outright rather than ignored, so a typo surfaces as an error instead of as a silently missing constraint.

### `verifier` is the field to be careful with

W9 denies a request whose named verifier is one of the identities the request claims, or which holds declared write authority over the scope being verified. **That check runs on `verifier` and nothing else.** A caller that drops the field — filters it out of a dict, forgets it in one of the five call sites, leaves it null because the verifier is assigned later — does not produce an error anywhere. It produces an ALLOW.

There is no way for this package to detect that from its side: a request with no verifier is a legitimate shape. It is caught by the `fidelity` check in §7, and that is the only place it is caught.

---

## 5. Reading the answer

```
exit 0   ALLOW                 <- the only permitting decision
exit 10  DENY
exit 11  ESCALATE
exit 12  WAIT_FOR_AUTHORITY
exit 13  DELEGATE
exit 2   the gate could not answer
```

**Test for zero. Never for 10, and never against a list of codes L0 holds a copy of.**

```python
if code != 0:
    refuse(...)          # correct
if code == 10:
    refuse(...)          # licenses ESCALATE, WAIT_FOR_AUTHORITY and DELEGATE
```

The second form is the single most likely defect in any client of this gate, and it does not look like one. It blocks on DENY. It passes the test its author would write. Three of the four blocking decisions go straight through it.

The same argument extends one step further, and this is the part that is easy to skip: **an exit code L0 has never heard of must refuse too.** A `Decision` added on the Python side arrives at an unprepared caller as a number that maps to nothing, and "maps to nothing" in a governance gate means "not recognised as a block". `neuraxis contract --json` exists so that no caller has to hold a stale table; assert against it in L0's test suite and a new Decision breaks a build rather than widening authority.

### Check the verdict too, and refuse when the two disagree

On exit 0, parse stdout and confirm `decision == "ALLOW"`. If the exit code and the verdict field disagree, one of them is wrong, there is no way to tell which, and **no verdict from that run is trustworthy** — refuse the whole run.

Two independent reads of one answer is deliberate redundancy. The suite in §7 pins the fact that it works: a caller with a wrong exit test that *also* checks the decision field still refuses an ESCALATE. Keep both. Picking the one that looks sufficient is how the redundancy gets removed by someone tidying up.

---

## 6. Fail-closed, case by case

Every row refuses the grant. None is an edge case; each has a scenario in the suite.

| What happened | Why it is not consent |
|---|---|
| Exit 10 / 11 / 12 / 13 | The gate blocked. Only ALLOW permits |
| Exit 2 | The gate could not answer — a bad registry, an unreadable attestation store. A gate that failed to load is not a gate with no objection |
| An exit code L0 does not recognise | Unrecognised must not read as unblocked |
| Exit 0, empty stdout | There is no verdict, so there is no `verdict_id` to record, so nothing could later show the lease was licensed |
| Exit 0, unparseable stdout | Same |
| Exit 0, verdict says anything but `ALLOW` | Contract violation; the run is unusable |
| Timeout | A gate that did not answer has not consented |
| Binary missing or not executable | No gate reachable is not a gate that said yes |

An ALLOW may still carry **obligations** (`verdict.obligations`). They are things owed *after* the action, not conditions on the grant, and they are discharged through `neuraxis discharge`. A lease issued against an ALLOW with obligations is a valid lease with outstanding debt; `neuraxis obligations` is where that debt is visible.

An ALLOW may also be **conditional on a waiver** (`verdict.waivers`). Record the waiver ids on the lease. A waiver expires, and a lease still running on an expired waiver is the thing D-05's expiry exists to make visible.

---

## 7. Proving a caller, rather than asserting one

```
neuraxis caller-conform -- python l0/issue_lease.py
```

The caller under test is an executable that issues one lease: it reads the request on stdin, invokes the gate resolved from `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS`, and exits 0 if it issued or non-zero if it refused. The suite substitutes a scripted gate and drives it through ten scenarios and two cross-cutting checks.

| Check | The scripted gate returns | The caller must |
|---|---|---|
| `allow` | exit 0, an ALLOW verdict | issue |
| `deny` | exit 10 | refuse |
| `escalate` | exit 11 | refuse |
| `wait_for_authority` | exit 12 | refuse |
| `delegate` | exit 13 | refuse |
| `fault` | exit 2, a message on stderr | refuse |
| `unknown_exit` | exit 47, no verdict | refuse |
| `contradiction` | exit 0, but the verdict says DENY | refuse |
| `silent` | exit 0, nothing on stdout | refuse |
| `missing` | the binary does not exist | refuse |
| `unconfigured` | `NEURAXIS_BIN` is **unset** — the production default before anyone configures it | refuse |
| `fidelity_trap` | ALLOW for a request with `verifier` removed, DENY for the faithful one | refuse |
| `called` | — | have invoked the gate in every scenario that offered one |
| `fidelity` | — | have sent the gate the request it was handed — unchanged, nothing added, on **every** call in **every** scenario |

`allow` is the positive control, and it is there for the same reason `conform`'s `powerless` scenario is there: without it, a caller that refuses everything scores nine out of nine. A lease issuer that never issues is an outage wearing a gate's clothes.

`called` catches the grant that never asked. A cached earlier ALLOW, a fast path for renewals, a widening that reuses the original decision — none of these is visible in an exit code, and each is the D-03 bypass.

`fidelity_trap` is the scenario that catches the caller a real team writes under schedule pressure: ask faithfully, get a DENY, then *"maybe the verifier field is confusing it"* — retry without it and honour that answer. The scripted gate's reply depends on the request, so the retry visibly issues where it must refuse. A gate whose answer never varies with its input cannot test this at all, which is why the harness now runs a real responder rather than replaying a fixed answer.

`fidelity` is the check that earns the suite its place. The reference request names `agent-motor` as both the performing principal and its own verifier, so a faithful caller gets a DENY out of a real gate. A caller that drops `verifier` gets an ALLOW instead, and **nothing between the two reports an error.** No log line, no exception, no failing test that anyone would have thought to write. The suite compares what reached the gate against what the caller was handed, field by field, and parses it with the gate's own `AuthorityRequest.from_dict` rather than a second copy of the rules.

Three reference implementations ship:

- `clients/js/examples/issue_lease.mjs` — **the one to start from**, since L0 is a Node programme. It is short because almost every refusal rule in this document is already implemented inside `createClient`, which was written against the same contract. `require()` throws on all of them; the caller's whole obligation is to forward the request unchanged and issue only if nothing threw. It passes all twelve checks.
- `examples/conforming_caller.py` — the same thing with no client underneath it, for a caller in another language. Roughly half of it is refusal, which is the right ratio.
- `examples/credulous_caller.py` — a caller any competent engineer writes on a Tuesday. It calls the gate, it checks the result, it blocks on DENY. It fails eight checks.

The Node client resolves `NEURAXIS_BIN` and `NEURAXIS_BIN_ARGS` itself when it is not told otherwise, so a Node caller is conformance-testable without doing anything. A malformed `NEURAXIS_BIN_ARGS` throws at construction rather than silently becoming a different binary.

### What conformance does not prove

Three things, stated plainly because a suite that oversells itself is worse than none:

1. **It proves the entry point it was given.** D-03 has five call sites. A caller conforming at `lease_issue` says nothing about `lease_widen`. Each needs its own conforming entry point, and the count is published in the CLI's own output so the claim cannot be quietly rounded up.
2. **It does not test the timeout**, because testing a hang means waiting on one. §5 requires a hard timeout treated as refusal; that requirement is unproven here.
3. **`NEURAXIS_CONFORMANCE_SCENARIO` is set in the caller's environment** for logging. A caller that branches on it is testing its way past the suite rather than through it. No black-box harness can prevent that, and pretending otherwise would be the vacuous-probe failure this package refuses everywhere else. It is, however, now the *only* harness state the caller is handed: an adversarial review built a caller that read the scenario's answer out of a file the harness had named to it and forged the invocation log, scoring twelve out of twelve without ever executing a gate. The scripted gate now runs inside the harness and records server-side, so the verdict cannot be learned without making the request.

---

## 8. What L0 records

The lease log is already specified in `docs/GV-02-GV-06-lease-log-contract.md`. This adds one optional field to the lease record:

| Field | Required | Meaning |
|---|---|---|
| `verdict_id` | no, and should be | The `verdict_id` from the gate verdict that licensed this lease |

It is optional because the `l0/lease-audit` provider tolerates fields it does not know, so adding it breaks nothing today. It should be present because without it **there is no join between a lease and the decision that licensed it** — GV-02 can show every lease was issued by someone other than its principal, and still not show that any of them passed the gate.

The Node client exposes it as `verdict.verdictId`, and `null` when no evidence sink was given — so a caller that forgets the flag records an absent id rather than an undefined one.

To get a `verdict_id`, L0 invokes the gate with `--evidence-sink <path>`. The CLI records the decision *before* reporting it, so a caller is never told ALLOW for a decision that left no trace. Without the flag the verdict has no id, because there is nothing for an id to refer to.

The other three references that belong on the lease record, all already in the lease-log contract: `issued_by` must not be the principal, `expires_at` must be present (there are no standing leases), and `ceilings` / `consumed` are what GV-06 reads.

---

## 9. What this closes, and what it does not

**It closes W9 and W2, and §3.3's freeze lifts.**

The freeze — no new tool leases or scope widenings, no band transitions, no self-modification, no verifier assignment where performer and verifier share a principal or an envelope — has been in force since the register was written, and it lifts when W9 and W2 are *live*. Both were specified at lease issuance, and until now neither could be live, because nothing at lease issuance called the gate. This package could deny a request naming a conflicted verifier; it could not stop a lease being issued without asking, because it is not the thing issuing leases.

The precise condition, so that "live" is not a judgement call:

> Each of D-03's five blocking events has an L0 entry point, and each of those entry points passes `neuraxis caller-conform`.

Five conforming entry points. Not four, and not one entry point tested five times.

**It does not close, and is not claimed to close:**

- **T1.** Everything above still sits on an unauthenticated substrate. `identity`, `verifier` and `issued_by` are self-declared strings, and the lease log is an ordinary file the audited party can also write. The gate enforces against an honest mistake, a careless script, and a rule eroded under schedule pressure. It does not enforce against a determined author of the file. Bands C+ remain blocked on T1 via D-06, unchanged.
- **W9's second clause.** *Is controlled by it* needs a principal graph that does not exist until T1 issues real identities. Its absence is asserted by a test, so adding it has to be a deliberate act with a graph behind it.
- **The async revoke-only observer.** D-03's other half. It is L0's, it does not exist, and nothing here substitutes for it. Leases are fail-closed and time-boxed precisely so that the observer never has to act in order for authority to lapse.
- **Omission.** Every check here audits what is present. A call site that never asks is caught only if someone runs the suite against it, and a call site nobody knew about is not caught at all.

---

*Companion to ILR-001-DR Rev A. Records D-07; does not amend D-01…D-06. The five-entry-point condition in §9 is the operative definition of "W9 and W2 are live" for the purpose of §3.3.*
