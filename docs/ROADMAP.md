# neuraxis — Roadmap

**Current:** v0.7.0 — evidence records close the verdict→audit edge. 4 of 10 controls wired, on an unauthenticated substrate until T1. 305 Python tests + 19 JS contract tests.
**To:** v1.0 (operational governance layer for BST-SA)
**Governing constraint:** one task at a time, CI green = done.

| Version | State |
|---|---|
| v0.1 gate core | **shipped** |
| v0.2 per-control windows | **shipped** |
| v0.3 provider harness | **shipped** — 4 of 10 controls wired |
| v0.3.1 Windows portability | **shipped** |
| v0.4 loop contracts | **Evidence Record shipped as v0.7.0**; Canonical Lesson / Weakness Signal still blocked on T3/T4 |
| v0.5 maw-js client | **shipped** |
| v0.6 service mode | not until a caller needs it |
| v1.0 hardening | **partially shipped as v0.6.0** — review done, fixable findings closed, structural limits documented |

---

## 0. The forcing constraint

`attestation_max_age: 24h` is global. Every band closes 24 hours after its last attestation, which means:

1. **A recurring assurance run is load-bearing, not optional.** Without it, Neuraxis denies everything by tomorrow. This is correct behaviour — an unproven control is not a control — but it makes the schedule part of the system, not part of the ops around it.
2. **A single global max age is wrong.** The kernel boundary probe is cheap and should run daily. A rollback drill or kill-switch drill is expensive and disruptive; forcing it daily guarantees it gets stubbed, and a stubbed drill is the vacuous-probe failure KBS-001 was written to prevent.

Per-control max age therefore precedes scheduling. Sequenced as v0.2 below.

---

## v0.2 — Make the model right before making it operational — SHIPPED

**Why first:** scheduling a wrong default cements it. Two small changes, one CI-green task.

| Change | Detail |
|---|---|
| Per-control `max_age` | `GV-01: {max_age: 24h}`, `GV-05: {max_age: 30d}`, etc. Registry-level default retained as fallback |
| Per-control staleness in `explain()` | Reasons must cite the control's own window, not the global one |

**Acceptance — met**
- [x] A registry with mixed windows resolves bands correctly
- [x] A control past its own window closes its band; one inside a longer window does not
- [x] Existing tests still green (no behaviour change when all windows are equal)

Two tests had to be retargeted: both assumed a 24h window for GV-04, which now carries 7d. That is the change working — a test that silently kept passing would have meant the window was not being consulted.

**Proposed windows** — operator decision, these are a starting point:

| Control | Window | Rationale |
|---|---|---|
| GV-01 identity, GV-02 authority, GV-03 evidence | 24h | Cheap, automated, high-value |
| GV-08 attestation (external probe) | 24h | KBS-001 §8 already runs daily |
| GV-04 verification | 7d | Changes with CI config, not daily |
| GV-06 containment, GV-09 provenance | 7d | Config-driven |
| GV-05 reversibility, GV-10 kill switch | 30d | Drills are disruptive; monthly is honest, daily is theatre |
| GV-07 ratification | 7d | Gate-log audit |

---

## v0.3 — Attestation providers — SHIPPED (harness + 4 of 10 wired)

**Why:** today attestations are recorded by hand with `neuraxis attest`. An operator typing `--result pass` is an assertion, not evidence. Until providers exist, the gate is well-built theatre.

One provider per control, each a script that fails closed and emits an attestation:

| Provider | Control | Source |
|---|---|---|
| `kbs-001/probe` | GV-01 | KBS-001 §8 adversarial probe, external org |
| `l0/lease-audit` | GV-02 | L0 lease issuance log — every action resolved to a grant |
| `kbs-001/sink-worm` | GV-03 | Evidence sink write test + WORM retention check |
| `nx/verifier-independence` | GV-04 | Sampled task audit: performer ≠ verifier |
| `nx/rollback-drill` | GV-05 | Executed rollback against a real mutation class |
| `l0/scope-budget` | GV-06 | Lease scope and budget ceilings enforced |
| `badf/gate-log` | GV-07 | Ratification records present for gated merges |
| `kbs-001/external-probe` | GV-08 | Signed attestation from the assurance org |
| `nx/lesson-provenance` | GV-09 | Every canonical lesson traces to evidence IDs |
| `nx/killswitch-drill` | GV-10 | Kill switch exercised end to end |

**Provider conformance rules** — inherited from the KBS-001 review, and enforced by a shared harness:

1. Fail closed — any unexpected condition is FAIL, never PASS
2. Positive control first — prove the check is live before scoring a negative
3. No vacuous probes — a check returning the same result for a powerful and a powerless identity is not a check
4. Emit evidence reference, never bare pass/fail

**Acceptance**
- [x] Provider harness with the four rules enforced by tests
- [x] A deliberately broken provider produces FAIL, not PASS — one test per failure mode: raises, dead check, vacuous probe, unreferenced pass, wrong return type
- [x] `neuraxis attest --from-provider <name>` replaces manual `--result`
- [x] `neuraxis providers` and `neuraxis assure`
- [x] `nx/verifier-independence` wired (GV-04)
- [x] `badf/gate-log` wired (GV-07) — five breach classes, record contract in `docs/GV-07-gate-log-contract.md`
- [x] `l0/lease-audit` (GV-02) and `l0/scope-budget` (GV-06) wired — one lease log, two audits, contract in `docs/GV-02-GV-06-lease-log-contract.md`
- [ ] GV-01/03/08 wired — **blocked on KBS-001 T1**
- [ ] GV-05/09 wired — **blocked on neuraxis v0.4**
- [ ] GV-10 wired — **blocked on KBS-001 E-13**

The six unwired controls are declared as `UnwiredProvider` rather than omitted, each naming its blocker. `neuraxis providers` therefore reads as a live dependency view, and `assure` refuses to attest them rather than skipping them quietly.

**Next wire-up:** GV-05 and GV-09 arrive with neuraxis v0.4 (blocked on T3/T4). The remaining four — GV-01, GV-03, GV-08 and GV-10 — all wait on KBS-001, and nothing in this package moves them.

**Every wired control so far specified its own evidence.** GV-07's gate log already existed; the L0 lease log does not, which makes its contract an input to the L0 design rather than a description of it. Specified afterwards, a provider audits whatever the implementation found convenient to record.

---

## v0.4 — Evidence Record and the loop contracts

The Execution → Learning boundary (ILR-001 §6.5), which is what makes GV-03 and GV-09 substantive.

| Artifact | Direction | Content |
|---|---|---|
| Evidence Record | Execution → Learning | Signed, sink-written: request, verdict, obligations discharged, outcome |
| Canonical Lesson | Learning → Execution | Kernel-promoted, provenance-bound, assumption-keyed |
| Weakness Signal | Learning → Evolution | Aggregated failure class, N distinct episodes minimum |
| Ratified Change | Evolution → Execution | Versioned, rollback-tested, ratification reference |

**The critical piece:** a kernel-side promoter that *recomputes* confirmation count, decay and assumption validity from raw evidence, and is the sole identity that can mark a lesson canonical. A mutable promoter that merely asserts criteria were met defeats K-04 entirely (ILR-001 §4.5).

**Acceptance**
- [ ] Obligations on an ALLOW are discharged or the record is marked incomplete
- [ ] A lesson without traceable evidence IDs cannot reach canonical
- [ ] Promoter recomputation tested against hand-computed fixtures
- [ ] Weakness Signal rejects single-episode inputs

**Blocked on:** T3/T4 decisions (lesson schema, promotion thresholds).

---

## v0.5 — maw-js client — SHIPPED (L0 integration outstanding)

**Why:** the CLI contract exists; BST-SA agents should not be shelling out by hand.

- Thin JS wrapper: `gate(request) -> verdict`, exit code mapped to a typed result
- Blocks on anything non-zero (the README's warning made structural: no caller can test only for `10`)
- L0 integration: lease check and GV-02 become the same question, asked once
- Verdict obligations surfaced to the agent as required follow-through

**Acceptance**
- [x] JS client contract tests run against the real CLI, not a mock
- [x] A new decision value added to the Python enum fails the JS tests rather than passing silently — verified by temporarily adding a sixth `Decision` and confirming the suite went red
- [x] `neuraxis contract` publishes the table so no client keeps its own copy
- [x] Unrecognised exit codes and unknown decisions throw rather than being read as passes
- [x] CI runs the client against the real gate on Linux and Windows
- [ ] L0 integration: lease check and GV-02 asked once — **blocked on the L0 lease API**
- [ ] One BST-SA workstream gated end to end — **needs a workstream to be chosen**

The client re-implements no rule. Band resolution, freshness, verifier
independence and the non-delegable floor stay in the Python gate; two
implementations of a governance decision is two governance decisions.

---

## v0.6 — Service mode (conditional)

Only if MCP Hub or a non-shell caller needs it. FastAPI wrapper over the same core, no second implementation of the logic.

**Do not build speculatively.** The CLI contract covers every current caller. Revisit when a caller exists that cannot shell out.

---

## v1.0 — Hardening

- Adversarial review of Neuraxis itself, in the style of the KBS-001 pass: what bypasses the gate, what makes a check vacuous, what fails open
- Threat model written down explicitly (currently implicit in the fail-closed tests)
- Attestation source conformance suite
- Operator runbook: what to do when a band closes at 02:00

**The question v1.0 must answer:** *what is the cheapest way for an agent to obtain an ALLOW it should not have?* Today the honest answer is "not call the gate at all" — which is KBS-001's problem, not Neuraxis's, but v1.0 should state where the seam is rather than leave it implied.

---

## Dependency on the T-queue

Neuraxis and the KBS-001 roadmap are one path, not two:

```
T1 kernel boundary ──→ v0.3 providers (GV-01/02/03/08)
T2 sealed exam     ──→ GV-04 provider, scorecard R term
T3/T4 lessons      ──→ v0.4 loop contracts, GV-09 provider
T5 self-mod        ──→ BAND-G opens under GV-07
```

v0.2 is the only item with no external dependency, which is a second reason it goes first.

---

## What running looks like

**Daily assurance run** — the load-bearing job:

1. Execute every provider whose window expires within 24h
2. Record attestations with evidence references
3. `neuraxis status` — report band state
4. Alert on any band that closed since the last run

**A closed band is not an incident by default.** It means a control stopped being proven, which is the system working. It becomes an incident when a band that ops depends on closes without anyone noticing — which is what the report is for.

**Weekly:** drift check on the registry against its ratified version (K-09 equivalent for Neuraxis config), and a scorecard recompute from the week's actual task measurements.

**Monthly:** rollback and kill-switch drills (GV-05, GV-10) — the expensive ones, on their own cadence.

---

## Not on the roadmap, deliberately

- **A web dashboard.** `neuraxis status` is the interface. A dashboard adds a surface that can display stale state convincingly.
- **Auto-attestation on successful task completion.** Tempting and wrong: it makes the system attest itself, which is the `V = 0` failure at the control layer.
- **Relaxing a window because a drill is inconvenient.** That is gate erosion. Change the window deliberately through a ratified registry change, or fix the drill.
