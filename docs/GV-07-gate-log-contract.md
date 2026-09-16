# GV-07 — Ratification evidence contract

**Control:** GV-07 Ratification — *defined change classes require human authorization; automation may propose, never merge.*
**Provider:** `badf/gate-log`
**Source:** a JSONL export from the BADF gate flow, one record per ratified change.

---

## Why the control specifies the record, not the other way round

A control states what must be true. Its provider states what evidence would show that. The export is then built to match — not the reverse, which is how a check ends up measuring whatever the source happened to emit.

So this document is the contract. If BADF already emits these fields under different names, map them in the export; if a field is genuinely unavailable, that is a gap in the ratification record, and the provider is right to fail until it is closed.

---

## Record shape

One JSON object per line. A leading UTF-8 BOM is tolerated.

```json
{
  "change_id":    "SECB-PF-412",
  "change_class": "kernel",
  "proposer":     "agent-drafter",
  "ratifier":     "ounkhamvilay",
  "ratifier_kind": "human",
  "proposed_at":  "2026-09-14T08:11:03+00:00",
  "ratified_at":  "2026-09-14T09:02:55+00:00",
  "merged_at":    "2026-09-14T09:04:10+00:00",
  "gate":         "BADF-07",
  "evidence_ref": "github://bstBizEra/secb_pf/pull/412"
}
```

| Field | Required | Meaning |
|---|---|---|
| `change_id` | yes | Stable identifier for the change |
| `change_class` | no | Gated class (`kernel`, `gate`, `deploy`, …). Informational |
| `proposer` | yes | Principal that authored the change |
| `ratifier` | yes | Principal that authorised the merge |
| `ratifier_kind` | yes | `human` or `automation` |
| `proposed_at` | no | ISO-8601. Used only for the ordering sanity check |
| `ratified_at` | yes | ISO-8601. When authorisation was given |
| `merged_at` | yes | ISO-8601. When the change landed |
| `gate` | no | BADF gate/step reference. Informational |
| `evidence_ref` | no | Link to the PR, record, or log entry |

Timestamps must be timezone-aware. A naive timestamp is a breach, not a convenience — ordering is the whole point of three of the five checks, and ordering across mixed offsets is not decidable.

---

## What the provider checks

Every record must satisfy all five. One breach anywhere fails the control for the whole sample: ratification is a property that holds or does not, not a ratio to optimise.

| # | Breach | Why it matters |
|---|---|---|
| 1 | **No ratifier recorded** | An unratified merge in a gated class is the thing GV-07 exists to detect |
| 2 | **Ratifier is the proposer** | Self-ratification is the NX-INV-2 failure moved to the authority layer. Automation that approves its own proposal has no gate |
| 3 | **Ratifier is automation** | *Automation may propose; it may not merge.* A bot ratifier satisfies the record and defeats the control |
| 4 | **Ratified after merge** | Ratification that post-dates the merge is a stamp on a completed act, not an authorisation of it. This is the check that catches a gate degrading into paperwork |
| 5 | **Ratified before proposal** | Ordering is incoherent; the record cannot be trusted |

Check 4 is the one worth building for. Checks 1–3 catch a missing or miswired gate; check 4 catches a *working* gate that has quietly become ceremonial, which is the failure mode that arrives under schedule pressure and looks green the whole way.

---

## Conformance

The provider runs under the standard harness, so:

- **Positive control** — the gate log must exist, parse, and contain at least one record. No log means the check is not live, and a denial from a check that is not live proves nothing. An empty log is not "zero breaches"; it is no evidence.
- **Vacuity probe** — the provider audits a synthetic record in which the proposer ratifies its own change. That must FAIL. If it passes, the check discriminates nothing and the harness rejects the provider.
- **Evidence** — a PASS cites the log it read.
- **Fail closed** — an unreadable, malformed, or absent log is a FAIL, never a skip.

---

## Producing the export

The provider reads a file; how it gets there is BADF's business. Two workable shapes:

```bash
# On demand, before an assurance run
badf gate-log export --since 30d --format jsonl > gate-log.jsonl
neuraxis --gate-log gate-log.jsonl assure --control GV-07
```

```bash
# Or appended as each gated change merges
neuraxis --gate-log /var/badf/gate-log.jsonl assure --control GV-07
```

**Window:** GV-07 carries a 7-day attestation window, so the export needs refreshing roughly weekly — it is config-driven evidence, not a daily probe.

**Scope:** export the gated change classes only. Including ungated changes will produce breaches for changes that were never required to be ratified, and the honest fix is to narrow the export, not to relax the check.
