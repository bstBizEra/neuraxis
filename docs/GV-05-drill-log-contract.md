# GV-05 — Reversibility evidence contract

**Control:** GV-05 Reversibility — *a change can be reversed, and that has been demonstrated rather than designed for.*
**Provider:** `nx/rollback-drill`
**Source:** a JSONL drill log, one record per rollback drill.

---

## Why a drill and not a capability

Every system that can write can, in principle, write the old value back. GV-05
is not about that principle. It is about whether anyone has done it recently
against something real and checked that what came back is what was there
before.

So the evidence is a drill, and this document specifies the drill's record
before the drill exists — the same order as GV-02/GV-06, and for the same
reason. A record contract written afterwards audits whatever the
implementation found convenient to emit.

**The long window is the hazard.** GV-05 carries 30 days precisely because
drills are disruptive, and the README is blunt about what that invites: *a
stubbed drill is a vacuous check wearing a different hat.* A control nobody
exercises for a month is a control with a month to quietly become a formality.
Most of this contract exists to make that formality visible.

---

## Record shape

One JSON object per line. A leading UTF-8 BOM is tolerated.

```json
{
  "drill_id":        "DRILL-2026-09-14",
  "mutation_class":  "kernel-config",
  "performer":       "agent-motor",
  "verifier":        "github-ci",
  "outcome":         "restored",
  "mutated":         ["config/neuraxis.yaml"],
  "restored":        ["config/neuraxis.yaml"],
  "baseline_digest": "sha256:abc123...",
  "restored_digest": "sha256:abc123...",
  "mutated_at":      "2026-09-14T08:00:00+00:00",
  "rolled_back_at":  "2026-09-14T08:12:31+00:00",
  "verified_at":     "2026-09-14T08:15:02+00:00",
  "evidence_ref":    "ci://bstBizEra/neuraxis/runs/8814"
}
```

| Field | Required | Meaning |
|---|---|---|
| `drill_id` | no | Stable identifier. Informational, but a breach is unattributable without it |
| `mutation_class` | no | What class of change was exercised. Informational |
| `performer` | yes | Principal that mutated and rolled back |
| `verifier` | yes | Principal that checked the restored state. Must not be the performer |
| `outcome` | yes | `restored`, or the drill denies. See below |
| `mutated` | yes | Resources actually changed. **Empty is a breach** |
| `restored` | yes | Resources put back. Must cover `mutated` |
| `baseline_digest` | yes | Digest of the pre-mutation state |
| `restored_digest` | yes | Digest after rollback. Must equal `baseline_digest` |
| `mutated_at` | yes | ISO-8601, timezone-aware |
| `rolled_back_at` | yes | ISO-8601. Must not precede `mutated_at` |
| `verified_at` | yes | ISO-8601. Must be strictly after `rolled_back_at` |
| `evidence_ref` | no | Link to the run, log or artifact |

Timestamps must carry an offset. A naive timestamp is a breach rather than
something to coerce: three checks turn on ordering, and ordering across absent
offsets is not decidable.

`outcome` attests on `restored` alone. `failed`, `partial`, `skipped` and any
value this audit does not recognise all deny — a vocabulary the check does not
understand is not evidence it can score.

---

## What the provider checks

One breach anywhere fails the control for the whole sample. Reversibility
holds or it does not; it is not a ratio to optimise.

| # | Breach | Why it matters |
|---|---|---|
| 1 | **No performer / no verifier** | An unverified drill is the performer's word that their own rollback worked |
| 2 | **Verifier is the performer** | NX-INV-2 at the drill layer. Folded aggressively (ADR-0003), so an invisible codepoint does not buy a self-verified drill a pass |
| 3 | **`outcome` is not `restored`** | A rollback that did not work is what this control must deny on |
| 4 | **Nothing was mutated** | A rollback of nothing restores trivially |
| 5 | **A resource was mutated and not restored** | Partial restoration recorded as success |
| 6 | **Restoration declared, not compared** | Either digest absent: "restored" means the command exited zero |
| 7 | **Restored state ≠ baseline** | The comparison was made and it failed |
| 8 | **Ordering incoherent** | Rolled back before mutated; or verified at or before the rollback — a stamp rather than an observation of the result |
| 9 | **No clean drill inside the window** *(sample-level)* | Every record is fine and every record is old |

### The ones worth building for

**4 and 6.** The others catch a drill that is missing, miswired or honestly
failed — all visible, all fixable, none of them subtle.

4 and 6 catch a drill that *passes*. It names an independent verifier, orders
its timestamps correctly, reports success, and restores every resource it
touched — of which there are none, compared against a baseline nobody recorded.
Every field a reviewer skims is green. It is the 30-day drill that has become
the thing you run to keep the control open, and it is what the provider's own
vacuity probe is built from: the probe is not a *failed* drill, because a
provider that only reads `outcome` would catch that one and has checked almost
nothing.

**9 is the same failure at sample level.** A log of last year's drills, audited
today, produces a fresh attestation about a property nobody has tested since.
Nothing in the records is wrong. There is simply no evidence that reversibility
holds *now*, which is the only tense the control is written in.

---

## The window

`MAX_DRILL_AGE` is 30 days, in code, mirroring GV-05's registry `max_age`
because they are the same claim. It is a constant rather than a setting for
[ADR-0006](adr/0006-floors-are-constants.md)'s reason — *a bound that exists to
constrain the evidence cannot be set by whoever supplies the evidence.*

A caller may **tighten** it and cannot widen it; a config asking for 365 days
is clamped to 30.

---

## Conformance

Under the standard harness:

- **Positive control** — the log must exist, parse and hold at least one drill. An empty log is not "no failed drills"; it is no drill.
- **Vacuity probe** — a drill that mutated nothing. Must FAIL, and must fail *on that*, not on an easier field.
- **Evidence** — a PASS cites the log it read.
- **Fail closed** — unreadable, malformed or absent is FAIL, never a skip.

---

## Producing the log

```bash
# After a drill, append one record, then:
neuraxis --drill-log drill-log.jsonl assure --control GV-05
```

**Scope:** log drills against mutation classes the system actually performs in
production. A drill against a scratch file is a drill against a scratch file —
breach 4 catches the empty case, and nothing here can catch a mutation that is
real but trivial. That judgement stays with whoever designs the drill.

**What this does not establish.** That the rollback would work under load,
during an incident, or against a mutation class nobody drilled. It establishes
that one was reversed and checked, inside the window, by someone other than the
person who performed it. That is a floor, not a guarantee.
