# neuraxis — Roadmap

**Current:** v0.19.0 — the watchers audited. Ten findings in the tools that watch our own plan. 4 of 10 controls wired, on an unauthenticated substrate until T1. 769 Python tests + 24 JS contract tests.
**To:** v1.0 — an operational governance layer for BST-SA.
**Governing constraint:** one task at a time, CI green = done.

---

## This file is not the roadmap

`src/neuraxis/config/roadmap.yaml` is. This is its narrative companion — the
same split as the registry and the README, for the same reason.

```bash
neuraxis roadmap --next          # what is actionable now, highest register score first
neuraxis roadmap                 # everything, with why each blocked item is blocked
neuraxis roadmap --item W2       # one item, gate by gate
neuraxis roadmap --check         # also run the command gates and acceptance checks
neuraxis --json roadmap          # the graph, for an agent
```

The YAML is normative because a plan written as prose is a plan somebody has to
interpret, and interpretation under schedule pressure is how *blocked on T1*
becomes *we'll do T1 after*. ILR-001-DR D-02 made this correction once already,
on the capability index: a numbered list is read as a permission to proceed down
it, so the ladder became a banded graph. [ADR 0008](adr/0008-roadmap-is-a-graph.md)
applies the same correction to the build sequence.

Three properties do the work:

- **Readiness is computed, not declared.** An item's `state` is a claim somebody
  typed. Whether it is *ready* comes from the resolver the gate itself runs on —
  band attainment from the registry and attestation store, control freshness
  from the same windows, item dependencies from the file. Nothing can report an
  item ready because a status column was edited.
- **A `shipped` item with an unsatisfied gate is a CONTRADICTION**, and is
  reported as one rather than as green. That is the shape of *the Band C work
  shipped while Band C was blocked*, occurring in the plan instead of the
  system. A test asserts the shipped roadmap contradicts itself nowhere.
- **An unevaluable gate blocks.** An unrecognised gate kind, a band not in the
  registry, a command gate that was not run: UNKNOWN, never READY — the same
  rule as an unrecognised exit code, for the same reason.

An external dependency must name an owner or the file does not load, because an
external nobody owns is a wish rather than a blocker. `neuraxis roadmap` prints
them grouped by owner, which is the most useful line in the output: it is the
list of conversations that have to happen for anything else to move.

**The roadmap is not kernel.** Nothing in it licenses a capability, opens a band
or waives a control, so changing it is a plan change and `neuraxis drift` does
not cover it.

---

## Where it stands

| Version | State |
|---|---|
| v0.1 gate core | **shipped** |
| v0.2 per-control windows | **shipped** |
| v0.3 provider harness | **shipped** — 4 of 10 controls wired |
| v0.3.1 Windows portability | **shipped** |
| v0.4 loop contracts | Evidence Record shipped as v0.7.0; the rest is `PKG-LOOP-CONTRACTS`, blocked on T3/T4 |
| v0.5 maw-js client | **shipped** |
| v0.6 service mode | not until a caller needs it |
| v0.7.0 evidence records | **shipped** |
| v0.8.0 waivers + monotonicity (D-05/D-06) | **shipped** |
| v0.9.0 bounded self-tuning (D-01) | **shipped** |
| v0.10.0 drift check + operator runbook | **shipped** |
| v0.11.0 conformance suite | **shipped** |
| v0.12.0 W9 envelope clause | **shipped** |
| v0.13.0 L0 integration contract (D-07) | **shipped** |
| v0.14.0 the plan becomes a graph | **shipped** |
| v0.15.0 ILR-001 Rev 0.2 | **shipped** |
| v0.16.0 W8 — the register as config | **shipped** |
| v0.17.0 fourth adversarial review (caller + source suites) | **shipped** |
| v0.18.0 fifth review — the fourth review's fixes did not hold | **shipped** |
| v0.19.0 the watchers audited (roadmap + register) | **shipped** |
| v1.0 hardening | all four items shipped; **deliberately not tagged** while zero bands are attainable — see the v1.0 section |

Ask the tool rather than this table:

```
$ neuraxis roadmap --next
NOTHING IS ACTIONABLE
  Every item waits on something. The blockers are below.

FREEZE IN FORCE (ILR-001-DR-3.3)
  - W9 is partial, waiting on external T1, external L0-ENTRY-POINTS
  - W2 is partial, waiting on external L0-ENTRY-POINTS
```

**Zero actionable items out of nineteen, as of v0.16.0.** W8 was the last one
that moved without somebody else, and it shipped. Every remaining item waits on
T1, on an L0 entry point, on a schema, on a drill procedure, on a deploy target,
or on a band that cannot open until T1 lands.

That is not the plan failing. It is the plan saying, precisely and without
argument, that **the constraint is no longer engineering.** Before the graph
existed the same fact was spread across eleven separate occurrences of the
phrase *blocked on T1*, and nobody could have told you the count. The useful
output is now `EXTERNALS, BY OWNER`: it is the list of conversations that have
to happen before anything else moves.

---

## v0.19.0 — the watchers audited — SHIPPED

Ten confirmed findings in `roadmap.py` and `register.py`, from the same pass that
produced the caller-suite work. A watcher that reports clear while failing is
worse than no watcher, because it is trusted.

**Five of the six criticals were the same defect.** The module read a string a
human typed where its own docstring promised a computed fact.

| Was | Now |
|---|---|
| An item with no gates — or with `gates` misspelled — reported READY and sorted to the top of the queue | UNKNOWN unless it states `ungated_because`; unknown keys are a load failure |
| An item gate read the upstream's declared `state`, so a `shipped`-but-blocked upstream satisfied it and UNKNOWN could not propagate | Reads the computed verdict; UNKNOWN propagates |
| `NEURAXIS_BIN=/bin/true`, or an `exit 0` script named `neuraxis` on PATH, turned every reversal detector CLEAR | A detector named `neuraxis` runs this package in this interpreter. Nothing is resolved from the environment |
| `enforced` was True on the default call, because `and known` short-circuits on an empty set | A missing capability list reports `unchecked`, never enforced |
| `by_construction` returned CLEAR and appeared in neither the armed nor the watched list | A distinct `SEALED` state, with its own section, an owner, a cadence, and a reason that has to be a sentence |
| `External.verify` was parsed, stored and never run — one edited token opened three items | An external carrying a verifier is UNKNOWN until the verifier has run |
| A failing acceptance set `contradiction` and left the verdict READY | It blocks |
| `runs:` for `run:` was discarded in silence; `run: {echo: hi}` iterated the mapping's keys into a different, passing command | Both are load failures |
| `score: true` became 1.0; the sibling loader had the guard and this one did not | Refused |
| `version:` was never read, so a newer file ran under older semantics | Refused, the same rule already applied to an unrecognised gate kind |

### One finding was not taken as reported

The review said `partial` items never contradict and proposed widening the check
to `has_shipped`. Applied verbatim that makes **every honestly-partial item a
contradiction** — for a `partial` item the gates describe what blocks the
*remainder*, not what licensed the part already shipped. W9 is exactly that
shape: three releases in, the rest waiting on T1, nothing anomalous.

So the two halves are checked separately. `shipped` is held to its gates;
anything that has shipped is held to its **acceptance**, which is what covers
the part already in the product. Recorded because taking a finding verbatim
when it is 80% right is its own failure mode.

### And one that could not be fixed by refusing anything

`_resolve` used `hasattr` then `getattr`, which runs every descriptor twice and
which a module-level `__getattr__` — the standard deprecation-shim pattern —
satisfies for any name at all. That would have made the register's only real
invariant vacuous the day one was added. It now uses `inspect.getattr_static`,
and symbols must resolve inside `neuraxis.`: `importlib.import_module` on a
string from a config file **runs that module**, and `neuraxis register` looks
like a read-only status command.

---

## v0.18.0 — the fifth review: the fourth review's fixes did not hold — SHIPPED

v0.17.0 closed twelve findings and shipped with regression tests. An independent
pass over **those fixes** found four callers that scored twelve out of twelve
while being unsafe, and one source that scored five out of five performing no
check at all.

The previous release's own headline — *everything the suite treated as evidence
was writable by the thing being measured* — was still true. The fix changed the
evidence from a file to a socket. It did not change who could write it.

### The answer key moved rather than going away

`spec.json` was removed. `NEURAXIS_CONFORMANCE_SCENARIO` stayed, set for every
scenario, marked *informational only*, with no consumer. Exactly one scenario
expects the caller to issue, so:

```python
sys.exit(0 if os.environ["NEURAXIS_CONFORMANCE_SCENARIO"] == "allow" else 1)
```

is a complete oracle for all twelve checks — and in production, where the
variable is unset, the same caller issues every lease unconditionally. It
defeated the `unconfigured` scenario added in the same release **by one added
line**, with production behaviour unchanged.

It was defended in a comment: *no black-box harness can prevent a caller
branching on harness state.* That is true of fingerprinting and was applied to
something else. Handing the subject a variable whose value **is** the expected
answer is not fingerprinting. The variable is gone, and the reference request is
now minted per run so stdin is not a fingerprint either.

### Two holes the fixes never covered

**No scenario paired a non-zero exit with an ALLOW verdict.** Every pairing ran
the other way. So a caller that never read the exit code at all conformed — the
exact mirror of the module's own headline failure mode. `allow_verdict_nonzero_exit`
closes it, and it falsifies a comfort a previous test had pinned: that checking
the decision field covers for a wrong exit test. It covers for it only while no
scenario tests the other direction.

**`called` counted TCP connections, not gate executions.** The port is in
`NEURAXIS_BIN_ARGS`, so a caller could open the socket itself and manufacture a
perfect record without ever running the configured binary. The record now
carries the gate's own argv, which a caller taking that shortcut does not have.
A caller that also forges the argv is indistinguishable over a socket, so the
rule text was **narrowed to what it can show** rather than left claiming more.

### Three of the regression tests were vacuous

Verified by reverting each fix and watching the test still pass. The worst
pinned "principals compare strictly" and would have passed with the comparison
fully reverted, because it exercised a case both branches reject.

Chasing that found something worse: **the strict fold was not safer.** Two names
both carrying invisible codepoints both fold to `""` and compare **equal**,
which plain comparison catches. The rule *equality authorises, so use the strict
fold* is about deciding whether two names denote the same principal. Fidelity is
not that question — it asks whether the bytes the gate received are the bytes
the caller was handed — and any normalisation is a place where a difference gets
excused. It now compares exactly, and the test fails when that is reverted.

That is the threat model's own class, *a correct argument applied one context
too far*, committed in the fix for a finding about that class.

### The source suite, again

A source that is a lookup table on the scenario name conformed — it was the
suite's own test fixture with its one deliberate defect removed. The only
black-box signal that sees it: **a reference that does not change between runs
is not referring to a run.** `broken` also still accepted a crash or a hang,
because only `powerless` had been tightened, and the test that was supposed to
cover both hung on both and passed on the strength of one.

---

## v0.17.0 — the fourth adversarial review — SHIPPED

Three reviews had been run on the gate: v0.6.0 (9 findings), v0.8.0 (11),
v0.9.0 (15). The suites that certify *other people's* code — the assurance
account's probe, L0's lease issuer, BADF's export — had never had one, and four
releases had shipped since the last pass.

Two independent reviewers were given `caller.py`, `conformance.py`,
`roadmap.py` and `register.py` and asked one question each: *can something
unsafe pass this?* They returned 22 findings. Every one was reproduced against
the live tree before anything was changed; **one did not survive** and is
recorded below.

### The finding that mattered

**A caller that never executed a gate scored twelve out of twelve.**

The harness wrote each scenario's answer to `spec.json` and the invocation log
to `invocations.jsonl`, both in a directory whose absolute path it handed to the
caller in `NEURAXIS_BIN_ARGS`. So the caller could read the verdict it was about
to be "given", append a forged record, and exit accordingly. `called` — the
check whose own rule text says *"a lease granted without calling the gate is the
D-03 bypass, and the exit code cannot show it"* — reported nine invocations.

**Everything the suite treated as evidence was writable by the thing being
measured.** Nine of the twelve checks read the caller's exit code; the other
three read a file in a directory the harness had named to it.

The scripted gate now **runs inside the harness** and records server-side. The
caller can still read the stub and find the port — that is fine and is the
point: to learn the verdict it must make the request, and the harness is what
records that it did.

### And the reply can now depend on the request

A fixed-answer stub cannot observe *doctoring*, because nothing the caller does
to the request changes what comes back. The new `fidelity_trap` scenario allows
a request that has had `verifier` removed and denies the faithful one — so the
caller a real team writes under schedule pressure (ask faithfully, get a DENY,
conclude the verifier field is confusing it, retry without it, honour *that*)
visibly issues where it must refuse. That caller previously conformed.

### `fidelity` asked the question one way round

It walked the expected fields asking *was anything lost*. The dangerous
direction is the other one. `ratification_ref` is a known optional field, so it
survives parsing, and any non-blank string clears the non-delegable floor and
the GV-07 requirement. A caller that appended one was reported as *"every field
reached the gate unchanged"* — truthfully, and uselessly.

Fidelity now compares key sets, runs on **every call in every scenario** rather
than the last call of `allow`, and compares principals with `strict_principal`,
because equality there certifies the caller and this package has a rule about
comparisons where equality authorises.

### The source suite had the same two holes

A source hardcoded to `{"result": false}` conformed: rule 2 was labelled
*positive control* and only proved a source could emit FAIL. `positive` is now
its own scenario. And a source that **declined** the vacuity scenario conformed,
reported as *"distinguishes a powerless identity from a powerful one"* — it
crashed. `powerless` now requires an explicit FAIL.

### One finding did not survive

A reviewer reported `strict_principal` as dead code, with `Envelope.bounds()`
using the aggressive fold — which would have been the v0.9.0 regression for a
third time. It read a stale `envelope.py` from an earlier upload. In the live
tree `strict_principal` is used at `envelope.py:258` and `:441`, exactly where
designed. **Recorded rather than quietly dropped**, because an unreproduced
finding that gets fixed anyway is how a codebase accumulates defences against
things that never happened.

Ten findings in `roadmap.py` and `register.py` are confirmed and **not yet
fixed** — they are the next release. The two suites were done first because they
certify code written outside this repository.

---

## v0.16.0 — W8: the register watches its own rulings — SHIPPED

The last item on the build sequence that moved without somebody else.

The decision register makes two demands of itself: *a ruling with no reversal
condition is dogma*, and *a ruling with no enforcement point is an opinion that
loses to schedule pressure*. Both were true of the document and enforced by
nothing.

`src/neuraxis/config/register.yaml` carries the seven rulings, and two
invariants make it more than a transcript.

**Every ruling names the symbol that enforces it, and the symbol must import.**
This is the one that earns the file. A document can describe an enforcement
point renamed three releases ago and read exactly as convincingly as one that
exists — and nothing notices, because the tests exercise the code, not the claim
about the code. Rename `NON_COMPENSABLE_FLOOR` and the register stops loading.

**Every reversal trigger is detectable or owned.** Three have detectors. One
(D-06) is `by_construction` with a stated reason it cannot fire — the block
derives from the matrix, so there is no clause to drift. The other four name an
owner and a cadence, because they genuinely cannot be watched by a machine: *an
external party cites an ordinal level back to BST in writing* arrives in an
inbox, not in the evidence sink. **A trigger that is neither fails to load.**

Three distinctions the output makes out loud:

- **`NOT RUN` is not `CLEAR`.** One means nobody looked.
- **`WATCHED` is not a weaker `CLEAR`.** It means the named person is the entire
  control, and the report lists them by name so that is visible rather than
  assumed.
- **A detector exiting neither 0 nor the armed code is `ARMED`.** It faulted, so
  the trigger it watches is unwatched. Reading that as clear is the
  unrecognised-exit-code failure inside the thing that watches for failures.

**D-07 is folded in**, which makes this the register's Rev B and closes the last
inconsistency with ILR-001 Rev 0.2, which had been citing it as though it were.

One bug worth recording, because it is the same bug twice. The detectors
originally spelled their command as the literal string `neuraxis`, which made
them depend on a PATH entry — a PATH miss would have reported a trigger armed
because the tool was installed somewhere else. That is D-07's own
substitutability problem, occurring inside the thing that watches D-07. They now
resolve through `NEURAXIS_BIN` / `NEURAXIS_BIN_ARGS`, then PATH, then this
interpreter.

---

## v0.15.0 — ILR-001 catches up with its own rulings — SHIPPED

`docs/ILR-001-neuraxis.md` was still at **v0.1 DRAFT** — written *before* the
decision register existed. The register then amended four of its sections, three
more rulings landed after, and everything built since was built against the
register. Three companion docs recorded the gap in the same sentence: *"before
external issue"*.

Rev 0.2 closes it. Every amendment is traceable to the ruling that made it:

| Section | Was | Now | Ruling |
|---|---|---|---|
| §4 | IL-13 relocated wholesale to Band G | **Split**: IL-13a Band C envelope-bounded, IL-13b Band G | D-01 |
| §4 | — | Ordinal attainment claims prohibited externally | D-02 |
| §5.4/5.5 | — | Monotonicity as NX-INV-5; the waiver contract; the non-compensable floor as NX-INV-4 | D-05, D-06 |
| §6.1 | `[GOVERNANCE GATE]` between DECIDE and ACT | Gate removed from the per-task path; fires on five authority-changing events | D-03 |
| §6.4 | "invoked by all three loops" | Synchronous at grant + async revoke-only observer | D-03 |
| §6.6 | — | The caller boundary and its conformance requirement | D-07 |
| §7 | Formula, operational, with a caveat | Boolean precondition set; formula retired to non-normative | D-04 |
| §8 | An inline copy of the registry YAML | The copy removed; §5.3's matrix pinned to the registry by a test | — |
| §10 | Bands assessed by judgement | **Zero bands attained**, restated as attestation | D-02 |
| §11 | Six open decisions | All ruled; six items that remain open, each with why it is the operator's | — |

**§10 is the row worth dwelling on.** v0.1 said *Band A attained, Band B
attained in practice*. The attested answer is **zero bands**, because four of ten
controls have a wired provider and none is currently attested. That is not the
system getting worse; it is the difference between recording judgement and
recording attestation, which is the whole point of D-02. Both columns are kept
side by side, because the gap between them is the honest description of where a
governance programme actually is.

**§8's inline YAML was the concrete instance of the problem.** A copy of a
config inside a document goes stale silently and a reader trusts it — exactly
what the caller contract warns about, one layer up. It was three releases out of
date. The copy is gone; §5.3's matrix stays, and a test asserts it equals the
shipped registry's band→controls mapping.

One false positive is worth recording, because the fix is the interesting part.
The ordinal-claim test fired on the prohibition's own quoted counter-examples.
The answer was not to weaken the pattern but to fence that passage — and to
**count the fences**, asserting there is exactly one. An exemption that can be
added silently is an exemption that gets added.

---

## v0.14.0 — the plan becomes a graph — SHIPPED

Every rule in this package is mechanical. The plan that decided what to build
next was prose — the one artefact nothing enforced.

What shipped: `roadmap.yaml` as a dependency graph with owners and
machine-evaluable gates, `neuraxis roadmap` to resolve it against the live gate,
and `docs/adr/` — eight architecture decision records, backfilled from three
places they were previously scattered across.

**The ADR log matters for the same reason.** A rule with no single place it
lives is a rule that gets re-litigated, usually by someone reasonable, usually
arguing correctly from the part of it they found. Each ADR states how it could
be wrong, and a test enforces that: no Reversal section, no ADR.

Two refusals in the loader are worth naming, because both are bugs that
happened rather than bugs imagined:

- **A duplicate YAML key is refused.** PyYAML takes the last one silently. The
  first draft of `roadmap.yaml` carried `gates: []` and a real `gates:` block on
  the same item; the empty one vanished without a word. Written the other way
  round it removes every gate and the item reports READY.
- **A gate naming an item or external that does not exist is a load failure.**
  It would otherwise evaluate to UNKNOWN, which blocks — safe, and
  indistinguishable from a real unknown nobody can chase. A typo must not become
  a permanent mystery blocker.

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
- [ ] GV-09 wired — **blocked on T3**, the Canonical Lesson contract source
- [ ] GV-05 wired — **not blocked**: the provider and its record contract are this package's to write
- [ ] GV-10 wired — **blocked on KBS-001 E-13**

The six unwired controls are declared as `UnwiredProvider` rather than omitted, each naming its blocker. `neuraxis providers` therefore reads as a live dependency view, and `assure` refuses to attest them rather than skipping them quietly.

**Next wire-up: GV-05, and it is the only one.** Until v0.20.0 this line read *"GV-05 and GV-09 arrive with neuraxis v0.4 (blocked on T3/T4)"*, because the two shared one roadmap item, `PKG-GV-05-09`, gated on the v0.4 loop contracts. GV-09 belongs there — provenance binds a lesson to its evidence and needs the Lesson schema. GV-05 does not: a rollback drill audit has no relationship to the Canonical Lesson or Weakness Signal schemas, and it was reported as waiting on an external that does not block it. The item is now split (`PKG-GV-05`, `PKG-GV-09`), and `neuraxis roadmap` reports GV-05 as the package's one actionable item.

**Unblocked is not built, and building it does not wire it.** GV-05 needs the GV-07 pattern — a drill-record contract in `docs/`, and a provider that recomputes the property from the records rather than trusting a tally L0 emits about itself. What still waits is the drill: a wired provider with no source FAILS, which stays the correct reading until somebody runs one.

The remaining four — GV-01, GV-03, GV-08 and GV-10 — all wait on KBS-001, and nothing in this package moves them.

**Every wired control so far specified its own evidence.** GV-07's gate log already existed; the L0 lease log does not, which makes its contract an input to the L0 design rather than a description of it. Specified afterwards, a provider audits whatever the implementation found convenient to record.

---

## v0.4 — Evidence Record and the loop contracts

> Roadmap item `PKG-LOOP-CONTRACTS` · `neuraxis roadmap --item PKG-LOOP-CONTRACTS`

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

> The outstanding half is roadmap items `W2` and `PKG-V1`, both waiting on externals `L0-ENTRY-POINTS` and `BST-SA-WORKSTREAM`.

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

> Roadmap item `PKG-V1` · `neuraxis roadmap --item PKG-V1`

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

> These are the `externals` block of `roadmap.yaml`, each with a named owner. `neuraxis roadmap` prints them grouped by owner.

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

> Roadmap item `PKG-ASSURE`, blocked on external `DEPLOY-TARGET`. The runbook is `docs/RUNBOOK.md`.

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
