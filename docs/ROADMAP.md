# neuraxis — Roadmap

**Current:** v0.13.0 - D-07: L0 calls this CLI at every authority grant, and `caller-conform` proves a caller acts on the answer. 4 of 10 controls wired, on an unauthenticated substrate until T1. 606 Python tests + 24 JS contract tests.
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
| v0.10.0 drift check + operator runbook | **shipped** |
| v0.12.0 W9 envelope clause | **shipped** |
| v0.13.0 L0 integration contract (D-07) | **shipped** |
| v0.6 service mode | not until a caller needs it |
| v0.11.0 conformance suite | **shipped** |
| v1.0 hardening | **all four items shipped** (v0.6.0 review, threat model, v0.10.0 runbook, v0.11.0 conformance suite). **Deliberately not tagged v1.0** while zero bands are attainable — see the v1.0 section |

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
- [x] Obligations on an ALLOW are discharged or the record is marked incomplete — **met by v0.7.0**, and this box was left unticked for three releases. `record_decision` refuses to issue an ALLOW owing EMIT_EVIDENCE that could not be written, and `audit_obligations` reports what is owed, what is paid, and a FAULT when the performer discharged its own. An unticked box that is actually done misrepresents state exactly as a stale dashboard does
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

- [x] Adversarial review of Neuraxis itself, in the style of the KBS-001 pass — **three of them**: v0.6.0 (9 findings), v0.8.0 (11), v0.9.0 (15). All 35 reproduced by execution before being fixed
- [x] Threat model written down explicitly — `docs/THREAT-MODEL.md`, shipped between v0.9.0 and v0.10.0
- [x] Attestation source conformance suite — **v0.11.0**, `docs/CONFORMANCE.md` and `neuraxis conform`
- [x] Operator runbook: what to do when a band closes at 02:00 — `docs/RUNBOOK.md`, v0.10.0

**All four are shipped, and this is still not v1.0.** The version stays on the
0.x track because a 1.0 would be read as a claim about the system, and the
system currently attains zero bands. Declaring 1.0 on a package where every
band is closed and six of ten controls have no provider is the ordinal
attainment claim D-02 prohibits, wearing different clothes. v1.0 is earned when
T1 lands and a band can actually open — not when the package's own checklist
runs out.

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

---

## v1.0 - Threat model written down (2026-09-16)

[`docs/THREAT-MODEL.md`](THREAT-MODEL.md) closes the v1.0 item *"threat model
written down explicitly (currently implicit in the fail-closed tests)"* and
answers the question v1.0 was told to answer. The answer has not changed: the
cheapest way to obtain an ALLOW you should not have is **not to call the gate**.
The document says so in §5.1 rather than leaving it implied.

Three things in it are new rather than restated:

**The 35 findings are classified, not listed.** Three adversarial reviews at
v0.6.0, v0.8.0 and v0.9.0, every finding reproduced by execution. §5.3 sorts
them into six classes - name comparison, a boundary that bounds nothing,
permissive by omission, counting and aggregation, two answers to one question,
parsing and coercion - each with the rule it yields. The list is a changelog;
the classes are reusable.

And the pattern behind all four critical findings was the same, which is the
part worth carrying: **a correct argument applied one context too far.** A
principal fold was safe because "a collision produces a denial" - true, until
the same fold was reused where a collision produces a grant. That happened
twice, a release apart. What to watch for in review is not an unguarded path
but a guard whose justification quietly stopped being true.

**§7 turns D-07 and D-08 into one decision.** This account has no paid plan and
no organisation. Repository rulesets are available on public repos at that tier
- demonstrated, not assumed, by creating one and having a direct push refused
with `GH013`. On a private repo at the same tier there is no ruleset and no
branch protection. So keeping the kernel repos public buys the enforcement
surface T1 needs, for free, today; going private removes it unless the account
upgrades. What is exposed is the design, not the state: `*.jsonl` is gitignored
and no attestation, waiver, envelope or evidence record is tracked.

**§8 is a residual risk register**, and R1-R6 are all Critical or High and all
closed by T1 and nothing else. That is the document's real conclusion: no
further work inside this package moves them, and has not since v0.3.

---

## v0.10.0 - The drift check becomes a control - SHIPPED

The previous entry made a release carry the SHA-256 of the kernel registry. An
artifact is not a control, so this turns it into one.

| Piece | Detail |
|---|---|
| `neuraxis validate` | reports `registry_path` and `registry_sha256` |
| `neuraxis drift` | `--expect <sha>` or `--expect-file REGISTRY-DIGEST.txt`; exit 0 match, 10 drift, 2 unreadable |
| `.github/workflows/drift.yml` | weekly, compares `main` against the latest release's ratified digest |
| `docs/RUNBOOK.md` | the v1.0 operator runbook |

**The digest is of the bytes on disk, not the parsed document.** It has to equal
what `sha256sum` prints, because the operator at 02:00 has `sha256sum` and a
number only this tool can reproduce would be useless to them.

**An expectation that cannot be read is an error, never a pass.** A `--expect`
that is not 64 hex characters, a `--expect-file` that is missing or carries no
`sha256` line, both flags at once: all exit 2. A drift check that reads an
unparseable expectation as "nothing to compare" reports clean for a file nobody
could parse, which is the vacuous probe in its cheapest form.

**The weekly job does not fail on any difference.** During development the
kernel legitimately moves ahead of the last release, so a check that went red
the moment it did would be red most of the time and ignored all of it - the
erosion this framework exists to prevent, arriving through its own monitoring.
A difference is reported every run and fails only once the kernel has been
unratified for more than 7 days, the same window the registry uses for its
config-driven controls. `workflow_dispatch` with `strict: true` fails on any
difference, for use before cutting a release.

### The runbook, and what it refuses to say

`docs/RUNBOOK.md` closes the last v1.0 documentation item. Its first line is
that **a closed band is not an incident by default** - it means a control
stopped being proven, which is the system working.

Two distinctions it exists to make at 02:00:

- **`attestation expired` versus `last attestation FAILED`.** The first is a
  scheduled run that did not happen; the second is a control that was holding
  and has stopped. Completely different problems, one line apart in `status`.
- **Proven-and-stopped versus never-proven.** Six controls have no provider and
  three of those wait on T1. If the blocker is GV-01, GV-03 or GV-08 there is
  no operational fix and no waiver path, and §6 says so rather than sending the
  operator looking for one.

§7 lists what never appears in a restoration sequence: editing the registry,
extending a window, waiving a non-compensable control, or re-running `attest`
by hand with `--result pass`. The last is the worst - it records an assertion
where a provider result should be, and `provenance` says `manual` in the
evidence forever.

**Acceptance - met**

- [x] The digest matches `sha256sum` on the same file
- [x] One changed byte is detected against the ratified digest
- [x] Every unreadable expectation exits 2, and none of them exits 0
- [x] A release-format `REGISTRY-DIGEST.txt`, a bare digest, and a BOM-prefixed file all parse
- [x] `drift` refuses to report on a registry that does not load

---

## v0.11.0 - Attestation source conformance - SHIPPED

The last unshipped v1.0 item, and the one piece of it that is T1 preparation
rather than package polish.

The four provider rules have been enforced since v0.3 by a harness that only
in-repo providers pass through. **The controls that matter most will not be
written here**: GV-01, GV-03 and GV-08 are attested by the external assurance
account, GV-02 and GV-06 by L0, GV-07 by BADF. None of them had a way to show
conformance before being trusted, which is how a programme ends up having
trusted an attestation source nobody tested - and a broken source is worse than
a missing one, because the missing one leaves the band closed while the broken
one reports it open.

| Piece | Detail |
|---|---|
| `neuraxis conform --control GV-nn -- <cmd>` | drives a source through its scenarios; exit 0 conforms, 10 does not, 2 cannot run |
| The contract | one JSON object in on stdin, one JSON attestation out on stdout |
| Scenarios | `live`, `broken`, `negative`, `powerless` - one per rule |
| `kind: probe \| audit` | registry-declared, on every control |
| `examples/conforming_source.py` | the reference implementation, to copy |
| `examples/vacuous_source.py` | the counter-example, kept on purpose |
| `docs/CONFORMANCE.md` | the contract, for whoever writes the source |

**Black box on purpose.** The assurance account should not have to write Python
to show its probe is honest, so a source is an executable and the suite drives
it from outside.

**The kind comes from the kernel.** A source that could declare its own kind
could declare its way out of the vacuity check - the finding class this package
has rediscovered most often - so `kind` is a registry field, and it defaults to
`probe`, so an omission tightens.

**The counter-example is in the repository deliberately.** A conformance suite
nobody has seen fail is itself an unverified check. `vacuous_source.py` emits a
well-formed attestation with a plausible evidence reference, every time, for
everyone, and the suite fails it on three rules while it *passes* rule 4 - a
source can satisfy the visible rule and none of the substantive ones.

**One bug found in the writing, and it was mine.** The CLI took the source as a
command line and split it with `shlex`, which treats a backslash as an escape -
so on Windows every source path silently became a different path and reported
as *missing* rather than as *failing*. A conformance suite that cannot run a
source on half its target platforms is worse than none. The command is now argv
after `--`, and a string is refused rather than guessed at.

**What it does not prove**, stated in the doc and in the tool's own output:
every scenario is implemented by the source, so conformance shows a source
*can* fail, not that it fails when it should. It closes the case that actually
happens - a check that was correct when written and has since stopped
exercising anything, still reporting green.

### Acceptance audit

All nine unticked acceptance boxes were re-read. **One was stale**: v0.4's
*"obligations on an ALLOW are discharged or the record is marked incomplete"*
was met by v0.7.0 and sat unticked for three releases. An unticked box that is
actually done misrepresents state exactly as a stale dashboard does, which this
roadmap rules out by name.

The other eight are genuinely blocked, and now say what by: T1 (GV-01/03/08),
T3/T4 (the three lesson boxes), E-13 (GV-10), the L0 lease API, and one
workstream that has to be nominated.

### And why this is not v1.0

All four v1.0 items are shipped. The version stays on the 0.x track anyway,
because **a 1.0 is read as a claim about the system, and the system attains
zero bands.** Six of ten controls have no provider and four of those wait on
T1. Declaring 1.0 here would be the ordinal attainment claim D-02 prohibits,
wearing different clothes.

v1.0 is earned when a band can actually open - not when the package's own
checklist runs out.

---

## v0.13.0 - the L0 integration contract (D-07) - SHIPPED

v0.12.0 closed with the observation that W9 was two-thirds enforced and that
**the freeze in ILR-001-DR §3.3 was unaffected**, because W9 and W2 are both
specified *at lease issuance* - L0's half, not this package's. The open question
was what shape that half should take.

**Ruling D-07: L0 shells out to `neuraxis gate`.** Four shapes were on the
table - an in-process import, an HTTP service, a generated static policy file,
and the CLI. The CLI wins for one reason worth keeping visible: it needs no new
gate code, so it is the only option where the freeze lifts on work L0 does
rather than work this package does. The contract exists, the Node client wraps
it, and `neuraxis contract` publishes the decision table so nothing on the far
side holds a copy that can go stale.

**And it moves the entire enforcement burden across a process boundary.** This
package can return DENY perfectly and license nothing, because the thing issuing
the lease is elsewhere, written by someone else, on the far side of an exit
code. So the deliverable here is not gate code. It is
[`docs/L0-LEASE-GATE-CONTRACT.md`](L0-LEASE-GATE-CONTRACT.md), plus a suite that
fails when a caller gets it wrong.

### `neuraxis caller-conform`

The mirror of `conform`. A caller is an executable that issues one lease; the
suite substitutes a scripted gate through `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS`
and drives it through ten scenarios and two cross-cutting checks. `escalate`,
`wait_for_authority` and `delegate` turn the README's standing warning - *test
for zero, not for a code list* - from a sentence into three failing scenarios.

Two checks are read from what reached the gate rather than from what the caller
returned:

- **`called`** - the caller invoked the gate in every scenario. A cached ALLOW,
  a fast path for renewals, a widening that reuses the original decision: none
  is visible in an exit code, and each is the D-03 bypass.
- **`fidelity`** - the object that reached the gate carries the same values the
  caller was handed, parsed with the gate's own `AuthorityRequest.from_dict`
  rather than a second copy of the rules.

**`fidelity` is why the suite earns its place.** The reference request names
`agent-motor` as both performer and its own verifier, so a faithful caller gets
a DENY. A caller that drops `verifier` gets an ALLOW - and nothing between the
two reports an error. No log line, no exception, no failing test anyone would
have thought to write. W9 is the highest-ranked item in the register and it is
switched off by a dict comprehension.

`examples/credulous_caller.py` ships for the reason `vacuous_source.py` does. It
calls the gate, checks the result, and blocks on DENY; its author would test it
against a DENY, watch it refuse, and ship it. It fails eight checks.

### The Node client is now conformance-ready by default

`createClient` resolves the gate from `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS` when
it is not told otherwise, and a malformed value throws at construction rather
than silently becoming a different binary. A client that could only be pointed
at a hard-coded path could never be driven through a DENY it did not arrange
itself. `clients/js/examples/issue_lease.mjs` is the reference Node caller and
passes all twelve checks - most of the contract was already implemented inside
`require()`, because it was written against the same contract.

Verdicts now carry `verdictId`, which §8 of the contract asks L0 to record on
the lease. Without it GV-02 can show every lease was issued by someone other
than its principal and still not show that any of them passed the gate.

### What lifts the freeze, stated so it is not a judgement call

> Each of D-03's five blocking events has an L0 entry point, and each of those
> entry points passes `neuraxis caller-conform`.

Five conforming entry points. Not four, and not one tested five times. The five
are published under `caller.blocking_events` in `neuraxis contract --json`, so
the count cannot be quietly rounded down. `lease_widen` is the one that gets
missed: a widening is a fresh grant arriving through a path that already holds
a valid lease, which is exactly why it feels like it does not need asking.

**T1 is unaffected.** Everything above still sits on an unauthenticated
substrate, and Bands C+ remain blocked on it via D-06.

---

## v0.12.0 - W9's third clause - SHIPPED

ILR-001-DR ranks **W9 the highest item in the register** (4.80) and describes it
in three clauses: *deny if the verifying principal is the performing principal,
**is controlled by it**, or **shares its envelope***.

| Clause | State |
|---|---|
| is the performer | shipped v0.6.0, hardened v0.8.0 against the invisible-codepoint bypass |
| **shares its envelope** | **v0.12.0** |
| is controlled by it | **deliberately absent** - see below |

The second clause became checkable the moment envelopes existed (v0.9.0) and
had not been checked. The gate now denies when the named verifier holds a
declared envelope giving it write authority over the scope being verified:

```
DENY IL-06 (BAND-B)
  - verifier 'agent-motor' holds declared write authority over 'bst-sa/pipelines'
    through envelope(s) ENV-MOTOR
  - NX-INV-2 (ILR-001-DR W9): a verifier that can change the thing it is
    verifying is a second party with a stake, not an independent one
```

**The fold runs the other way here, and that is the whole point.** The
authorising question - *does this envelope bound you?* - compares principals
strictly, because a collision there widens a grant to a principal that was
never named. This question - *does this verifier already hold authority over
what it is verifying?* - denies on a match, so a collision must fail closed and
the comparison folds aggressively. `Envelope.bounds()` and `Envelope.may_bind()`
are therefore two methods rather than one with a flag, and a test asserts they
disagree exactly where intended: `agent-motor` and `agent-mötor` stay two
principals for `bounds()` and collapse into one for `may_bind()`.

Reusing one for the other would have been the same mistake the v0.9.0 review
found, in the same file, one release later. The threat model calls this class
*a correct argument applied one context too far*; this is what acting on it
looks like.

**A scope nobody can parse is not an absence of authority.** On the authorising
path, a scope carrying a traversal component or an invisible character is
outside every envelope. Here the same answer would read as "this verifier holds
nothing", which is a conclusion nobody is entitled to draw from a string nobody
can compare - so an uncomparable scope returns *every* active envelope binding
the verifier, and the request is denied.

### The clause that is missing, and why it stays missing

*Is controlled by it* needs a principal graph saying which identities control
which. No such graph exists until KBS-001 T1 issues real identities, and a
check that always answers "no control relation known" is precisely the vacuous
probe this package refuses everywhere else. It would pass every test and check
nothing.

Its absence is asserted by a test, so adding one has to be a deliberate act
with a real graph behind it rather than a line someone adds to make a docstring
match. The same test pins a nearby judgement call: two principals whose
envelopes share a *signer* are **not** treated as one controlling the other.
That may be the right relation to encode later; it is not a guess to make now.

### What this does and does not move

W9 is two-thirds enforced. **The freeze in ILR-001-DR §3.3 is unaffected**, and
this is worth being plain about: the freeze lifts when W9 and W2 are live, and
both are specified *at lease issuance* - which is L0's half, not this package's.
Neuraxis can deny a request that names a conflicted verifier. It cannot stop a
lease being issued without asking, because it is not the thing issuing leases.

So the next decision on this path is not T1. It is **whether L0 gets a lease
API the gate is called from** - the question that lifts a freeze that has been
in force since the register was written.
