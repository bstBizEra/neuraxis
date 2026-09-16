# neuraxis — Roadmap

**Current:** v0.9.0 - bounded self-tuning: IL-13a admissible from Band C inside a declared, machine-evaluable envelope. 4 of 10 controls wired, on an unauthenticated substrate until T1. 492 Python tests + 19 JS contract tests.
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
| v0.7.0 evidence records | **shipped** |
| v0.8.0 waivers + monotonicity (D-05/D-06) | **shipped** |
| v0.9.0 bounded self-tuning (D-01) | **shipped** |
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

---

## v0.8.0 - The exception path (ILR-001-DR D-05, D-06) - SHIPPED

**Why this and not more provider wiring.** The v0.6.0 review established that
wiring a provider onto an unauthenticated substrate grows forgeable surface
without growing what is proven, so the remaining six wait on T1. D-05 does
not: it is the ruling that the gate needs an exception path, and that the
path must ship *before* it is needed, because a gate retrofitted onto a
system that already holds the authority is a gate that gets waived.

| Piece | Detail |
|---|---|
| `Waiver` | control, bands, accountable human, compensating control, ratification reference, issued_at, hard expiry, optional `renews` |
| Non-compensable floor | GV-01/02/03/08 unwaivable, as a constant in code. A registry may add to the set; it cannot remove from it |
| Bounds | max TTL 90d, max 2 active, max 1 renewal - ceilings in code, tightenable by registry, never loosenable |
| Self-waiver ban | a waiver never licenses its own issuer or accountable principal (NX-INV-2 applied to the exception path) |
| Monotonicity | `requires(band)` must be a superset of every prerequisite's, asserted on load |
| Single root | exactly one band may declare no prerequisite, so the staircase reaches the ground |
| Non-delegable floor | a non-delegable capability's band must require every control, so IL-32 cannot be re-homed somewhere cheaper |
| Reporting | `BandStatus.conditional`, `Verdict.waivers`, `neuraxis waivers` (exit 10 when a reversal trigger is armed), `neuraxis waive` |

**Acceptance - met**

- [x] A waiver licenses a band whose control is unattested, and says so in every verdict it touches
- [x] A non-compensable control is refused at load, at issue, and with no registry block present at all
- [x] A waiver expires with nothing running; the boundary resolves against the waiver
- [x] The self-waiver ban survives case, whitespace, invisible codepoints and NFKC confusables
- [x] Renewal beyond depth 1 refused; parallel renewals of one root refused; tiled unlinked waivers on one scope refused
- [x] Over the active cap, every waiver is void and the denial says so
- [x] Obligations are unchanged by a waiver
- [x] Band status computed once per evaluation, at one instant

**What a second adversarial review found, and what it cost.** Eleven findings,
two of them critical, every one reproduced by execution before it was fixed.
The two that mattered:

1. **One invisible codepoint defeated both the self-waiver ban and NX-INV-2.**
   `"agent-drafter​"` renders identically to `"agent-drafter"`, survives
   `strip()`, and compared unequal. The verifier-independence bypass needed no
   waiver at all and had been live since v0.6.0 - the single rule ILR-001-DR
   D-04 calls the cheapest high-value control BST can ship. Principal names now
   fold through NFKC, drop format characters, casefold and drop combining
   marks; a record containing an invisible character is refused outright.
2. **Deleting four lines of YAML made the integrity controls waivable.** The
   non-compensable set was read from the registry and defaulted to empty, so
   omission - not argument - inverted D-06. The floor is now a constant in
   code that configuration can only add to.

The remaining nine: renewal stars, waiver tiling, a second root band, a
non-delegable capability re-homed to a cheaper band, direct construction
bypassing every parse-time check, a `bands` string doing substring matching,
a voided waiver set reported as a plain missing attestation, waiver ids
re-derived rather than carried, and an unmemoised traversal costing 11 million
status computations at 30 bands. All closed, all with a regression test in
`tests/test_waiver_review.py`.

**What the exception path still cannot do.** `issued_by`, `accountable` and a
request's `identity` are self-declared strings. The self-waiver ban compares
what the record claims against what the request claims, and binds neither to
an authenticated subject. It stops an honest mistake and a careless script,
not a determined author of the waiver file. That is T1's job, and it is the
same limit as everything else here: the substrate is unauthenticated until the
kernel boundary lands.

**Not built, deliberately:** a waiver for KBS-001 D-06 (the single code owner).
The mechanism exists; issuing the record now would spend one of two active
slots licensing a band that is blocked on four non-compensable controls
anyway. It is issued when T1 lands and GV-07 is actually what stands in the
way - not before, because an active waiver that licenses nothing is exactly
the decorative governance this package is against.

---

## v0.9.0 - Bounded self-tuning (ILR-001-DR D-01) - SHIPPED

**Why this next.** D-01 was the last structural ruling in the register with no
implementation. Until now the package shipped Option B - all of IL-13 in Band
G - which the register calls right in principle and unenforceable in practice:
teams adjust thresholds, retry budgets and routing weights as ordinary learning
work, so a rule forbidding it gets reclassified as "configuration" and done
outside the register. An unenforceable prohibition is worse than none, because
it moves the activity out of view.

| Piece | Detail |
|---|---|
| Capability split | `IL-13a Self-Tuning` (BAND-C, `envelope_bounded: true`) and `IL-13b Self-Modifying` (BAND-G) |
| Envelope | principal, capability, signer, manifest ref, target prefixes, parameter intervals, hard expiry |
| Declared in advance | a request naming no envelope, or declaring no adjustment, is denied |
| Machine-evaluable | vacuous targets, traversal components, empty limit sets, non-finite bounds and bounds above 1e12 are all refused at load |
| Not self-amended | `signed_by` may not be the principal it bounds, compared on the aggressive fold |
| One principal | the envelope must bound *every* identity the request claims, so tuning on another's behalf is out |
| Registry cross-check | `authority.envelope_required` must agree with `envelope_bounded`, or the registry does not load |
| D-01 trigger | out-of-envelope denials counted per envelope over 90d; `neuraxis envelopes --audit` exits 10 when armed |
| CLI | `neuraxis declare`, `neuraxis envelopes [--audit]`, `gate --envelope-ref --adjust k=v` |

**The distinction that took a review to find.** There are now two ways this
package compares principal names, and they must not be the same function:

- Where a collision must produce a **denial** - verifier independence, the
  self-waiver ban, the envelope self-signing check - the fold is aggressive
  (NFKC, invisibles dropped, case-folded, marks stripped). Over-folding fails
  closed.
- Where a collision produces an **authorisation** - "does this envelope bound
  you", "is this signer on the allowlist" - the comparison is NFC only. Nothing
  is case-folded and no accent is stripped, because `agent-cortex` and
  `agent-cörtex` are two principals and the second must not inherit the first's
  envelope.

The first cut used the aggressive fold for both, and its docstring carried a
safety argument that was true in v0.8 and silently false in v0.9. That is the
failure mode worth naming: not a missing check, but a correct argument reused
one context too far.

**What a second adversarial review found.** Fifteen findings, two critical,
every one reproduced by execution before it was fixed.

1. **`../` walked straight out of every envelope.** `hippocampus/lessons/../../etc/shadow`
   starts with `hippocampus/lessons/`, so prefix matching called it covered.
   Any envelope authorised any path in the tree. Paths are now compared
   component-wise, and a scope carrying a traversal component, a mixed
   separator, percent-encoding or an invisible character is refused outright
   rather than resolved.
2. **The fold, as above.**

Then: an empty `limits` map loading as a bound that bounds nothing; `[0, 1e308]`
as the infinity bypass with more zeroes; a register built outside the registry's
policy silently voiding both the TTL ceiling and the signer allowlist (now
re-checked at use, not only at load); a one-token YAML deletion disabling D-01
with no load error and no failing test, guarded by a tautology marked
`pragma: no cover`; an empty `adjustments` producing an ALLOW whose audit trail
said "0 adjustment(s) inside the declared limits"; one appended `{` making every
subsequent audit raise instead of reporting an armed trigger; naive timestamps
dropped where unparseable ones were counted; the threshold missing from the
audit result, so a clean report from a raised threshold was indistinguishable
from a clean sink; `performer="   "` blanking the obligation audit's
self-discharge check; and an unknown field in an envelope record being ignored,
so a typo'd `limits_` loaded as an envelope with no numeric bound at all.

**Acceptance - met**

- [x] A declared bound authorises an in-range adjustment and denies an out-of-range one
- [x] No envelope, no adjustment, wrong principal, wrong capability, expired, or policy-breaching all deny, and all carry the marker the trigger counts
- [x] Prefix matching cannot be walked out of, and cannot be widened by a lookalike name
- [x] A registry cannot disable the split by omission, loosen the TTL ceiling, or empty the signer allowlist
- [x] The trigger arms at two denials against one envelope and survives a malformed sink line

**What it still cannot do.** `signed_by` is a string in a JSONL file the bounded
component can also write. Nothing verifies a signature and nothing dereferences
`manifest_ref`. Populating `authority.envelope_signers` narrows who may be
*named*; it does not make the naming authentic - so, unlike the rest of this
package's limits, this one does not close when the allowlist is filled in. It
closes when T1 gives the envelope file a kernel write path and real signing
keys.

**Left unrestricted on purpose.** The shipped registry ships
`envelope_signers: []`, and `neuraxis validate` warns about it. Naming a
principal there today would be a list of strings pretending to be an allowlist,
since no principal registry exists until T1. The warning is the honest state.

---

## Version control - the process layer catches up (2026-09-16)

Nine releases had gone to `main` by direct push. That is this framework's own
rule broken by the thing that defines it: *automation may propose; it may not
merge*, and the performer was merging its own work with nothing independent
between proposal and effect. The process layer was running at `V = 0` while the
package spent four releases making `V = 0` impossible for everyone else.

Fixed, mechanically rather than by convention:

- **Ruleset `main: automation may propose, it may not merge`**, active, no
  bypass actors. Pull request required, **0 required approvals** (a sole owner
  cannot approve their own PR, so 1 would deadlock every merge - D-06's shape
  again), all seven status checks required, branch must be current before
  merge, no force-push, no deletion. Verified by execution: a direct push to
  `main` is now refused with `GH013`.
- **Tags** `v0.3.1` ... `v0.9.0`, retroactive. `v0.1`-`v0.3` landed inside the
  initial commit and cannot get one; `v0.3.1` is the first independently
  referenceable version.
- **`release.yml`** on tag push: checks out the tag, runs the suite and the
  gate self-check *against that commit*, builds sdist and wheel, and records
  the SHA-256 of the kernel registry as a release asset.

The last one is the substantive part. `## What running looks like` above
prescribes a weekly "drift check on the registry against its ratified version",
and that sentence was meaningless while no version was ratified. Now a release
carries `REGISTRY-DIGEST.txt`, and the weekly check is one `sha256sum`.

Full runbook in [`docs/RELEASE.md`](RELEASE.md), including what the ruleset
does **not** claim: one person opening and merging their own pull request is
weaker than two-person review, and nothing here authenticates an author. Same
limit as everywhere else - it closes at T1.
