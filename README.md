# neuraxis

**BST Neuraxis — Intelligent Loop Registry and Governance Gate.** Reference implementation of ILR-001. **v0.5.2.**

Capability is licensed by the governance controls paired to it. A capability whose controls do not hold a current passing attestation is denied — mechanically, at the call site, not by instruction to an agent.

```
pip install -e ".[dev]"
neuraxis validate
```

---

## The one rule

> A capability band is not enabled until every governance control paired to it holds a current passing attestation.

Nothing else in this package matters if that is bypassable, so everything here is fail-closed: absence, expiry, failure, future-dating, an unknown capability, a malformed registry and an internal exception all produce the same answer — **DENY**.

---

## Quickstart

```bash
# Nothing attested: every band blocked. This is the correct initial state.
neuraxis --attestations attestations.jsonl status

# Record the controls that actually hold, with evidence references.
neuraxis --attestations attestations.jsonl attest \
    --control GV-01 --result pass --issuer operator --evidence-ref kbs-001/run-881

# Ask the gate.
neuraxis --attestations attestations.jsonl gate \
    --capability IL-06 --identity agent-drafter --role drafter \
    --intent "run the coffee cost pipeline" --verifier github-ci --rollback-tested
```

```
ALLOW IL-06 (BAND-B)
  - BAND-B attained; drafter granted; 5 controls current
  obligations: emit-evidence-record, independent-verification, tested-rollback
```

Name the performer as the verifier and it closes:

```
DENY IL-06 (BAND-B)
  - verifier 'agent-drafter' is the performer
  - NX-INV-2: V = 0 when performer and verifier are the same identity
```

---

## Attestation windows

Each control carries its own window, because windows are set by the cost of the check:

| Control | Window | Why |
|---|---|---|
| GV-01, GV-02, GV-03, GV-08 | 24h | Cheap, automated, high-value |
| GV-04, GV-06, GV-07, GV-09 | 7d | Config-driven; they change with CI, not daily |
| GV-05, GV-10 | 30d | Drills are disruptive |

A single global window forces every control onto the cadence of the cheapest one, which is how expensive drills end up stubbed — and a stubbed drill is a vacuous check wearing a different hat. `neuraxis validate` prints the effective windows.

---

## Providers

An attestation recorded by hand is an operator asserting something. A **provider** establishes it and cites the evidence.

```bash
neuraxis providers          # coverage of the control set
neuraxis assure             # run every due provider, record, report band changes
neuraxis assure --control GV-04 --force

# Wired providers read evidence files; point them at yours
neuraxis --task-log task-log.jsonl --gate-log gate-log.jsonl \
         --lease-log lease-log.jsonl assure
```

```
CONTROL  PROVIDER                        STATE     WINDOW
GV-01    kbs-001/probe                   UNWIRED   1d
                                         blocked on: KBS-001 T1 — kernel boundary probe
GV-02    l0/lease-audit                  WIRED     1d
GV-04    nx/verifier-independence        WIRED     7d
GV-06    l0/scope-budget                 WIRED     7d
GV-07    badf/gate-log                   WIRED     7d
...
4 of 10 controls have a wired provider.
```

**UNWIRED is deliberate and visible.** A control whose real source does not exist yet is declared rather than omitted, so coverage is honest and `assure` refuses to attest it instead of skipping it quietly. The output doubles as a live view of the T-queue.

### The four conformance rules

Every provider runs through a harness that enforces these. They come from the KBS-001 review, where three of five assurance probes passed unconditionally:

1. **Fail closed** — any unexpected condition is FAIL, never PASS. A provider that raises, returns the wrong type, or trips the harness itself produces FAIL.
2. **Positive control** — the provider must prove its check is live before any negative result is scored. A denial from a dead check proves nothing.
3. **Vacuity probe** — the provider must run its own check against a condition that *must* fail. If that probe passes, the check discriminates nothing and is rejected as vacuous.
4. **Evidence** — a PASS without a reference is an assertion, and is refused.

```python
class MyProvider(Provider):
    control, name = "GV-06", "l0/scope-budget"

    def positive_control(self) -> bool:
        return self.source_reachable()          # is the check live?

    def vacuity_probe(self) -> ProviderResult:
        return self.audit(deliberately_bad)     # must FAIL

    def check(self) -> ProviderResult:
        return self.audit(self.real_source())
```

### Wired providers

**`nx/verifier-independence` (GV-04)** audits a task log for `performer != verifier`, treats an empty or missing log as not-live rather than as a trivial pass, and its vacuity probe audits a synthetic self-verified record.

**`badf/gate-log` (GV-07)** audits the BADF gate log for genuine human ratification — *automation may propose, never merge.* Five breach classes: no ratifier, self-ratification, an automation ratifier, ratification that post-dates the merge, and ratification that pre-dates the proposal.

The fourth is the one worth building for. The first three catch a missing or miswired gate; ratified-after-merge catches a **working** gate that has quietly become ceremonial — the failure that arrives under schedule pressure and looks green the whole way. The record contract is in `docs/GV-07-gate-log-contract.md`.

**`l0/lease-audit` (GV-02)** and **`l0/scope-budget` (GV-06)** read one L0 lease log with two record kinds. Authority joins actions to leases and checks that each action ran *after* its lease was issued, before expiry, inside granted scope, under a lease no principal issued to itself. Containment checks that ceilings were declared, covered every resource consumed, were not exceeded, and were not widened by the principal they bound.

Both recompute from raw records rather than trusting a compliance tally L0 emits about itself — that would be performer-verifies-itself moved to the evidence layer. Contract: `docs/GV-02-GV-06-lease-log-contract.md`.

**The two breaches worth building for** are the ones where the record looks complete and the property has quietly gone: an action authorised *after* it ran, and a ceiling that was recorded and not applied.

> **A wired control with no source fails.** `neuraxis assure` exits non-zero when a provider's evidence file is absent, because a check that is not live has not passed. Supply `--task-log` and `--gate-log`, or scope the run with `--control`.

---

## Python API

```python
from neuraxis import AuthorityRequest, AttestationStore, CapabilityGuard, load_registry

guard = CapabilityGuard(load_registry(), AttestationStore.from_file("attestations.jsonl"))

request = AuthorityRequest(
    intent="promote lesson to canonical",
    identity="agent-cortex", role="cortex", capability="IL-11",
    scope="hippocampus/lessons", verifier="github-ci", rollback_tested=True,
)

with guard.require(request) as verdict:       # raises CapabilityDenied on any non-ALLOW
    promote_lesson()
    # verdict.obligations tells you what you now owe: evidence, provenance, rollback
```

Decorator form, for capabilities exercised at a fixed call site:

```python
@guard.capability("IL-11", role="cortex", verifier="github-ci", rollback_tested=True)
def extract_lesson(episode): ...
```

Routing on the verdict instead of raising:

```python
verdict = guard.check(request)
if verdict.decision is Decision.WAIT_FOR_AUTHORITY:
    open_ratification_batch(request)
```

---

## The JSON contract (maw-js, L0, CI)

The CLI is the language-neutral boundary — one implementation, callable from anywhere.

```bash
echo '{"intent":"run pipeline","identity":"agent-drafter","role":"drafter",
       "capability":"IL-06","scope":"bst-sa","verifier":"github-ci",
       "rollback_tested":true}' \
  | neuraxis --json --attestations attestations.jsonl gate -
```

| Exit | Decision |
|---|---|
| 0 | ALLOW |
| 10 | DENY |
| 11 | ESCALATE |
| 12 | WAIT_FOR_AUTHORITY |
| 13 | DELEGATE |
| 2 | error — registry fault, bad input, unreadable attestations |

**Callers must test for zero, not for a code list.** A caller that blocks only on 10 will act on an ESCALATE.

Unknown request fields are rejected rather than ignored, so a typo (`rollbackTested`) fails loudly instead of silently dropping a constraint.

### Node / maw-js

`clients/js` is a zero-dependency Node client over the same contract:

```js
import { createClient } from "@bst/neuraxis-client";
const gate = createClient({ attestations: "attestations.jsonl" });
await gate.withCapability(request, async (verdict) => { /* obligations on verdict */ });
```

Its decision table is asserted against `neuraxis contract` in CI, so adding a
`Decision` in Python fails the JS tests instead of arriving as an exit code the
client maps to nothing. See `clients/js/README.md`.

---

## The contract command

```bash
neuraxis --json contract
```

Emits the decision/exit-code table, the permitting decision, obligations, risks
and accepted request fields. Non-Python clients assert against this rather than
keeping their own copy — a copy is a thing that can silently go stale, and a
stale exit-code table in a governance client means an unrecognised block read
as no block.

---

## Wiring it into CI

```yaml
- name: Neuraxis gate
  run: |
    neuraxis --attestations "$ATTESTATIONS" gate - < request.json
    # non-zero blocks the job; no interpretation needed
```

Attestations are produced by the checks named in the registry — `kbs-001/probe`, `l0/lease-audit`, `nx/rollback-drill` and the rest. Each check writes its own result:

```bash
neuraxis attest --control GV-08 --result "$RESULT" \
    --issuer kernel-boundary-probe --evidence-ref "$GITHUB_RUN_ID"
```

---

## What is in the box

| Module | Responsibility |
|---|---|
| `registry` | Load and fully validate `neuraxis.yaml`. No partial or default registry. |
| `attestation` | Attestation store, freshness, newest-wins, JSONL persistence |
| `resolver` | Band attainment over the dependency graph; reports the **root** blocker |
| `gate` | The synchronous governance gate — the only decision point |
| `guard` | Call-site enforcement: context manager and decorator |
| `scorecard` | `I = C x R x L x A x V x G`, used as a veto |
| `providers` | Provider contract, conformance harness, builtin providers |
| `cli` | The JSON/exit-code contract |

---

## Design decisions worth knowing

**Newest-wins attestations.** A fresh FAIL supersedes an older PASS. A max-of-passes policy would let a dead control look alive.

**The root blocker is reported, not the requested band.** Asking for IL-33 with an empty store tells you `BAND-A` is missing GV-01 — because BAND-G is never the real problem.

**`V = 0` when performer equals verifier.** Not a penalty, a zero. The product structure means it vetoes everything downstream. This is the failure that ends most agentic self-improvement projects, so it is encoded rather than documented.

**The scorecard is a gate, not a KPI.** Multiplying ordinal scores is not statistically meaningful. `effective` is diagnostic; `gate_band()` is the supported use. Do not put the number on a dashboard.

**`on_missing_attestation: allow` is rejected at load.** Fail-closed is not configurable. A registry that permits it is not a Neuraxis registry.

**Registry faults deny.** An unloadable registry is treated as absent, and an absent registry denies everything — rather than falling back to a permissive default.

---

## Honest limits

- **This enforces at the call site, not at the credential.** A component that never calls the gate is not governed by it. Mechanical enforcement of the boundary itself is KBS-001's job (lease scope, kernel separation); Neuraxis assumes that boundary already holds.
- **Six of ten controls have no real provider yet.** `neuraxis providers` says which and why. Until they are wired, those controls can only be attested by hand — which is an assertion, not evidence.
- **Attestations are as good as the checks that produce them.** The harness enforces the four rules mechanically, but it cannot tell whether a provider is auditing the right thing. It catches a check that cannot fail; it does not catch a check that measures the wrong property.
- **The JSONL attestation file is a local mirror, not an audit trail.** Under KBS-001 the authoritative sink is WORM-backed. Do not treat this file as evidence of record.
- **Band thresholds in the registry are a starting point**, not calibrated values. Set them from your own measurements.

---

## Tests

```bash
python -m pytest -q --cov=neuraxis --cov-report=term-missing
```

**Python:** 229 tests, 94% coverage. **JS client:** 19 contract tests. The suite includes explicit **positive controls** — `test_allows_when_everything_holds`, `test_ratified_non_delegable_capability_is_allowed`, `test_guard_decorator_runs_the_body_on_allow`. Without them, a gate that denied unconditionally would pass every other assertion in the suite. `tests/test_failclosed.py` asserts that faults become denials rather than implicit allows.

---

## Registry

`src/neuraxis/config/neuraxis.yaml` is **kernel** under KBS-001 (K-04 family). Agents hold no write path to it. Changing a band's requirements, the non-delegable floor, or a scorecard threshold is a ratified kernel change, not a code change.

ILR-001 has the full framework: the 33 capabilities, the seven bands, the ten governance controls, the Capability–Authority Gate matrix, the three loops and their contracts.
