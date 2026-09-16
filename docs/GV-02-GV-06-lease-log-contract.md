# GV-02 / GV-06 — L0 lease-log evidence contract

**Controls**
- **GV-02 Authority** — *every action resolves to an explicit scope grant (lease) before execution.*
- **GV-06 Containment** — *blast radius bounded by scope, sandbox, budget and rate limit.*

**Providers:** `l0/lease-audit` (GV-02, 24h window) · `l0/scope-budget` (GV-06, 7d window)
**Source:** one JSONL export from the L0 enforcement layer.

---

## Written before L0, on purpose

The BADF gate log already existed when GV-07 was wired, so its contract described something real. L0 is still being designed, and that makes writing this contract **more** useful rather than less: specify the evidence now and L0 is built emitting it; specify it afterwards and the provider ends up auditing whatever the implementation found convenient to record.

So treat this as an input to the L0 design, not a description of it. Where a field is awkward to produce, the interesting question is usually whether the underlying property is actually being enforced — not how to reshape the record.

---

## One log, two record kinds

Both controls read the same file. A lease record carries the grant; an action record carries a use of it. Splitting them into two exports would create two things that have to agree, and the join is where both audits get their teeth.

```json
{"record":"lease","lease_id":"L-0031","principal":"agent-motor","issued_by":"l0-gate",
 "issued_at":"2026-09-14T08:00:00+00:00","expires_at":"2026-09-14T09:00:00+00:00",
 "scope":["repo:bstBizEra/secb_pf","tool:git"],
 "ceilings":{"tokens":200000,"wall_seconds":900,"tool_calls":200},
 "consumed":{"tokens":143221,"wall_seconds":410,"tool_calls":88},
 "ceilings_amended_by":null,
 "evidence_ref":"l0://lease/L-0031"}

{"record":"action","action_id":"a-1","lease_id":"L-0031",
 "at":"2026-09-14T08:12:00+00:00","scope":"tool:git"}
```

A leading UTF-8 BOM is tolerated. Timestamps are ISO-8601 and must carry an offset — ordering is what four of these checks turn on, and ordering across absent offsets is not decidable.

### Lease record

| Field | Required | Meaning |
|---|---|---|
| `record` | yes | `"lease"` |
| `lease_id` | yes | Identifier actions reference |
| `principal` | yes | Who the lease authorises |
| `issued_by` | yes | Who granted it. Must not be the principal |
| `issued_at` | yes | When the grant took effect |
| `expires_at` | yes | When it lapses. **No standing leases** |
| `scope` | yes | List of granted scope strings |
| `ceilings` | yes (GV-06) | Declared limits per resource |
| `consumed` | yes (GV-06) | Actual usage per resource |
| `ceilings_amended_by` | no | Principal that widened the ceilings, if any |
| `evidence_ref` | no | Link to the L0 record |

### Action record

| Field | Required | Meaning |
|---|---|---|
| `record` | yes | `"action"` |
| `action_id` | yes | Identifier |
| `lease_id` | yes | The lease claimed to authorise it |
| `at` | yes | When it executed |
| `scope` | yes | The scope string it exercised |

---

## GV-02 — what the authority audit checks

| # | Breach | Why |
|---|---|---|
| 1 | Action references no lease, or one not in the log | The plain case GV-02 exists to detect |
| 2 | **Action executed before its lease was issued** | Post-hoc authorisation. The lease exists, so the record looks complete — but the action was not authorised when it ran |
| 3 | Action executed after the lease expired | D-03 makes leases fail-closed and time-boxed; expiry revoking by default is the whole mechanism |
| 4 | Action scope not in the lease's granted scope | A lease that does not bound scope is not a grant |
| 5 | Lease issued by its own principal | Self-issuance is NX-INV-2 at the authority layer. A component that can grant itself authority has none |
| 6 | Lease with no `expires_at` | A standing grant. D-03's reversal trigger watches median TTL rising; an absent TTL is that failure already complete |

Breach 2 is the one worth building for, and it is the same shape as GV-07's ratified-after-merge: the gate still runs, the record still fills in, and the authorisation has quietly stopped preceding the act.

## GV-06 — what the containment audit checks

| # | Breach | Why |
|---|---|---|
| 1 | Lease with no declared ceilings | An unbounded grant. Containment that declares no limit bounds nothing |
| 2 | **Consumption exceeded a declared ceiling** | The ceiling was advisory, not enforced. This is KBS-INV-3 measured: a control enforced by instruction is not a control |
| 3 | Consumed a resource with no ceiling | Bounded on tokens, unbounded on everything else |
| 4 | Ceilings amended by the principal they bound | D-01's `envelope_amended_by_the_same_principal_it_bounds`, at the lease layer |

Breach 2 is the point of the control. A ceiling that is checked and refused shows up as an action that never happened; a ceiling that was exceeded and the work completed anyway shows that L0 recorded a limit and did not apply it.

---

## Conformance

Both providers run under the standard harness:

- **Positive control** — the log must exist, parse, and hold at least one record of the kind that provider audits. GV-02 needs at least one action; GV-06 needs at least one lease. No records is not "no breaches", it is no evidence.
- **Vacuity probe** — GV-02 audits a synthetic action that ran before its lease was issued; GV-06 audits a synthetic lease that blew its token ceiling. Both must FAIL.
- **Fail closed** — an unreadable, malformed or absent log is a FAIL.
- One breach anywhere fails the control for the whole sample. Authority and containment are properties that hold or do not.

---

## Producing the export

```bash
l0 lease-log export --since 24h --format jsonl > lease-log.jsonl
neuraxis --lease-log lease-log.jsonl assure --control GV-02
neuraxis --lease-log lease-log.jsonl assure --control GV-06
```

**Windows differ deliberately.** GV-02 carries 24h: authority is cheap to check and high-value, so it should be proven daily. GV-06 carries 7d: ceilings are config-driven and change with the lease catalogue, not hourly. Export accordingly — a weekly export will not keep GV-02 current.

**Scope the export to leased actions.** Including unleased background activity produces breaches for actions that were never required to hold a lease. The honest fix is to narrow the export, or to decide those actions should in fact be leased.
