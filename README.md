# neuraxis

**BST Neuraxis — Intelligent Loop Registry and Governance Gate.** Reference implementation of ILR-001. **v0.7.0.**

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

## Evidence records — the feedback edge

Before v0.7 the gate was write-only: it issued verdicts and nothing recorded
them, so no later cycle could observe that an ALLOW had been issued — let alone
that what it owed went unpaid. That is why three obligations were labels.

```bash
neuraxis --evidence-sink evidence.jsonl gate --capability IL-06 ... 
#  ALLOW IL-06 (BAND-B)
#    verdict 514e47ce66dbc807
#    obligations: emit-evidence-record, independent-verification, tested-rollback

neuraxis --evidence-sink evidence.jsonl obligations
#  1 ALLOW(s) owing 3 obligation(s); 0 discharged
#    OUTSTANDING emit-evidence-record — IL-06 by agent-drafter (514e47ce66dbc807, ...)

neuraxis --evidence-sink evidence.jsonl discharge \
    --verdict 514e47ce66dbc807 --obligation emit-evidence-record \
    --by github-ci --evidence-ref sink://...
```

**An ALLOW that cannot be recorded becomes a DENY.** A permission granted with
no trace is exactly the condition GV-03 exists to rule out, so a sink write
failure refuses the caller rather than quietly permitting an unaudited action.
A block that cannot be recorded stays a block — nothing was permitted.

**Self-discharge is a fault**, compared stripped and case-folded: paying your
own obligation is NX-INV-2 at the obligation layer. So is a discharge for a
verdict never issued, or for an obligation that verdict did not owe.

> **This is not an attestation of GV-03.** The sink is an ordinary append-only
> file the audited party can also write, so omission stays undetectable. It
> creates the record stream GV-03 is meant to protect. Building it before the
> WORM sink is deliberate: when T1 lands there is something for it to make
> tamper-evident, rather than a protected sink with nothing in it.

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

## What an adversarial review found

v0.6.0 is the result of attacking v0.5.2 from a fresh context. Every fix below
corresponds to a confirmed exploit, and each has a regression test in
`tests/test_hardening.py`.

| Fixed | Was |
|---|---|
| Attestation ties resolve to FAIL | An **appended** PASS with an equal timestamp overtook a FAIL — the one poisoning attack that survives an append-only WORM sink, since it requires no edit at all |
| Readers `split("\n")` | `splitlines()` also breaks on `\v \f \x85 \u2028`, which are legal inside a JSON string and invisible to `wc`, `diff` and any per-line hasher — the loader and an auditor saw different record sets |
| Verifier compared to every claimed identity, stripped and case-folded | Naming a fictitious `performer` bought self-verification; `"agent-x "`, `"Agent-X"` and `" "` all passed |
| `rollback_tested` must be a JSON boolean | `"rollback_tested": "false"` is a non-empty string, so spelling the word satisfied NX-INV-3 |
| GV-06 iterates ceilings, requires `consumed` to be a dict, rejects non-finite | Omitting `consumed` passed; `{}`, `[]`, `0` passed; `NaN` lost every comparison silently |
| GV-07 treats `ratified >= merged` as a breach | A stamp emitted at the merge instant passed the check built to catch rubber-stamping |
| GV-07 rejects a present-but-empty `proposed_at` | `""` and `0` skipped the ordering check while `"garbage"` was a breach — backwards |
| A band with `requires: []` is rejected at load | It was unconditionally attained: a capability grant wearing a band's name |
| `register()` cannot shadow a wired builtin | Builtins were not in `PROVIDERS`, so the name guard missed them; extras run last, so the shadow's attestation always won |

## Honest limits

- **This enforces at the call site, not at the credential.** A component that never calls the gate is not governed by it. Mechanical enforcement of the boundary itself is KBS-001's job (lease scope, kernel separation); Neuraxis assumes that boundary already holds.
- **Omission is undetectable, and it is the limit that matters.** Every provider audits the records present in a file and has no way to know which records are absent. There is no sequence number, record count, hash chain or external anchor. A one-line fabricated log produces the same PASS as a complete export. So each wired provider proves a *conditional* — *if* this file is the complete and faithful record, *then* the property held — and nothing here establishes the antecedent.

  **GV-03 (WORM evidence sink) and GV-08 (external attestation) are exactly the two unwired controls that would establish it.** Until they land, wiring more providers increases the surface that can be forged without increasing what is actually proven. Read "4 of 10 wired" as four well-specified audits on an unauthenticated substrate, not as four controls in force.
- **Six of ten controls have no real provider yet.** `neuraxis providers` says which and why. Until they are wired, those controls can only be attested by hand — which is an assertion, not evidence.
- **Identity, role and risk are accepted as asserted.** `role` is a free string on the request; nothing binds it to `identity`, and `identity` is never authenticated. `risk` defaults to LOW and is requester-supplied, so `escalate_at_risk` escalates only requests that volunteer being critical. Binding these is L0's job, not the gate's.
- **A registry or evidence path is whatever the caller passes.** `--registry` accepts any file. Process-level integrity — which binary, which config, which environment — is outside this package and belongs to the kernel boundary.
- **Obligation discharge is recorded, not verified.** Since v0.7 an ALLOW and its obligations are written to the sink and `obligations` reports what went unpaid — but a discharge record asserts that a duty was met without proving it. The join catches self-discharge, forged verdict ids and obligations never owed; it does not check that the cited evidence exists.
- **The vacuity probe is provider testimony.** It proves a probe exists and reports failure, not that the probe exercised `check()`. No in-process harness can close that.
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

## Waivers - the exception path

A programme with no exception path grows an undocumented one. A path with no
expiry becomes the architecture. So Neuraxis has one, and its bounds are in
code rather than in configuration.

```bash
neuraxis waive --id W-D06 --control GV-07 --band BAND-G \
  --accountable "OP-Vily" --issued-by ops-console \
  --compensating "break-glass merge logged to the evidence sink; E-12 alert on use" \
  --ratification-ref KBS-001/7.7 --ttl 30d

neuraxis waivers        # exit 10 while a reversal trigger is armed
neuraxis status         # the band now reads CONDITIONAL, never ATTAINED
```

A waiver names the control, the bands it covers, a human accountable for it, a
compensating control, a ratification reference and a hard expiry. Every one of
those is required; a blank is a malformed record, not a lenient one.

**What a waiver cannot do.**

| | |
|---|---|
| Waive GV-01, GV-02, GV-03 or GV-08 | Non-compensable (ILR-001-DR D-06). A constant in code: a registry may add controls to the set, never remove them. An append-only sink a human promises not to rewrite is a rewritable sink |
| Outlive 90 days | Ceiling in code. One renewal, then the matrix gets re-cut instead |
| License its own issuer or accountable principal | NX-INV-2 applied to the exception path. Principal names are compared after NFKC folding with format characters dropped, so an invisible codepoint does not make one principal into two |
| Exist three at a time | Over the cap every waiver is void, and the denial says so rather than reporting the control as merely unattested |
| Cancel a per-request obligation | A waiver says a control cannot currently be proven at programme level. It does not say an individual request need not comply |
| Make a band read as plainly attained | `BandStatus.conditional`, `Verdict.waivers` and the ALLOW's first reason line all say the authority is conditional |

**And its limit.** `issued_by`, `accountable` and a request's `identity` are
self-declared strings on an unauthenticated substrate. The self-waiver ban
compares what the record claims against what the request claims. It stops an
honest mistake and a careless script; it does not stop a determined author of
the waiver file. Nor does anything here stop someone appending two junk
waivers to void a third party's legitimate one - the cap is fail-closed, which
makes it a denial-of-service in the hands of anyone with write access to the
file. Both are the same limit as the evidence sink's: the substrate is
unauthenticated until KBS-001 T1 issues real identities.

## Envelopes - bounded self-tuning (IL-13a)

`IL-13` is split. `IL-13b Self-Modifying` stays in Band G behind full
assurance. `IL-13a Self-Tuning` is admissible from Band C, and only inside a
bound declared in advance by someone other than the component it constrains.

```bash
neuraxis declare --id ENV-CORTEX --principal agent-cortex --capability IL-13a \
  --signed-by ops-console --manifest-ref "bst-sa/manifest#v7" \
  --target hippocampus/lessons --limit retry_budget=1:5 --ttl 30d

neuraxis gate --capability IL-13a --identity agent-cortex --role cortex \
  --intent "tune retry budget" --scope hippocampus/lessons/thresholds \
  --verifier github-ci --rollback-tested \
  --envelope-ref ENV-CORTEX --adjust retry_budget=3
#  ALLOW IL-13a (BAND-C)
#    - bounded by envelope ENV-CORTEX (scope hippocampus/lessons/thresholds;
#      1 adjustment(s) inside the declared limits)

neuraxis envelopes --audit    # exits 10 when the D-01 trigger is armed
```

**Why a split rather than a ban.** The wholesale move of IL-13 to Band G is
right in principle and loses in practice: teams adjust thresholds, retry
budgets and routing weights as ordinary learning work, and a rule that forbids
it gets reclassified as "configuration" and done anyway, outside the register.
An unenforceable prohibition is worse than none, because it moves the activity
out of view. So the line is drawn where it can be held, and it is mechanical.

**What an envelope cannot do.**

| | |
|---|---|
| Exist implicitly | A request naming no envelope, or declaring no adjustment, is denied. "Declared in advance" means the default is not permission |
| Match everything | A target of `*`, `/` or `**` is refused at load, and so is an empty limit set: a boundary that bounds nothing is permission wearing a boundary's name |
| Be walked out of | Targets are compared component by component. A scope with a `..`, a mixed separator, percent-encoding or an invisible character is refused rather than resolved |
| Bound without bounding | A limit must be a finite interval no wider than 1e12. `[0, 1e308]` is the infinity bypass with more zeroes |
| Be widened by its holder | `signed_by` may not be the principal it bounds, compared on the fold that collapses lookalikes |
| Be borrowed | The envelope must bound *every* identity the request claims, so naming someone else as `performer` unlocks nothing |
| Outlive its mission | 90-day ceiling in code; a registry may tighten it and cannot raise it |
| Escape its registry | The TTL ceiling and signer allowlist are re-checked where the envelope is used, not only where it was loaded |
| Be disabled by omission | `authority.envelope_required` must agree with `envelope_bounded`, or the registry does not load |

**Two principal keys, and why.** Where a collision must produce a **denial** -
verifier independence, the self-waiver ban, envelope self-signing - names are
folded aggressively (NFKC, invisibles dropped, case-folded, marks stripped), so
over-folding fails closed. Where a collision produces an **authorisation** -
"does this envelope bound you", "is this signer on the allowlist" - the
comparison is NFC only: `agent-cortex` and `agent-cörtex` are two principals,
and the second must not inherit the first's envelope.

**And its limit.** `signed_by` is a string in a JSONL file that the bounded
component can also write. Nothing here verifies a signature and nothing
dereferences `manifest_ref`. Filling in `authority.envelope_signers` narrows who
may be *named*; it does not make the naming authentic. Unlike the rest of the
limits in this README, this one does not close when the allowlist is populated -
it closes when KBS-001 T1 gives the envelope file a kernel write path and real
signing keys.

## Drift — is the kernel registry the ratified one?

The registry is kernel under KBS-001. The roadmap prescribes a weekly drift
check of it "against its ratified version", which was an inert sentence while
no version was ratified. Releases now carry the SHA-256 of the exact bytes that
shipped, so the check is one comparison:

```bash
neuraxis validate            # ... registry: .../neuraxis.yaml   sha256: 7be0bd56...

gh release download v0.10.0 --pattern REGISTRY-DIGEST.txt
neuraxis drift --expect-file REGISTRY-DIGEST.txt
#  MATCH: the registry on disk is the ratified one.        -> exit 0
#  DRIFT: ... Do not attest anything against it ...        -> exit 10
```

The digest is of the **bytes on disk**, not the parsed document, so it equals
what `sha256sum` prints. The operator at 02:00 has `sha256sum`; a number only
this tool can reproduce would be useless to them.

**A mismatch is not automatically an incident**, and the two causes need
opposite responses: either someone changed the kernel without a release, or you
are not running the version you think you are. `docs/RUNBOOK.md` §4 has both.

An expectation that cannot be read is an **error**, never a pass. A drift check
that reports clean for a file nobody could parse is the vacuous probe in its
cheapest form.

The weekly `drift` workflow reports a difference every run and fails only once
the kernel has been unratified for more than 7 days — the same window the
registry uses for its config-driven controls. A check that went red the moment
the kernel moved would be red most of the time and ignored all of it, which is
the erosion this package exists to prevent, arriving through its own monitoring.

## Operating it

[`docs/RUNBOOK.md`](docs/RUNBOOK.md) — what to do when a band closes at 02:00,
what every exit code means, how to tell *proven-and-stopped* from
*never-proven*, and the five things never to do to make a red go away.

The short version: **a closed band is not an incident by default.** It means a
control stopped being proven, which is the system working. It becomes an
incident when a band something depends on closes and nobody notices.

## Conformance — can this attestation source be trusted?

The four provider rules have been enforced since v0.3, by a harness that only
in-repo providers pass through. **The controls that matter most will not be
written here**: GV-01, GV-03 and GV-08 are attested by the external assurance
account, GV-02 and GV-06 by L0, GV-07 by BADF.

```bash
neuraxis conform --control GV-01 -- python examples/conforming_source.py
#  PASS  live       rule 4 - emit an evidence reference, never a bare pass/fail
#  PASS  broken     rule 1 - fail closed
#  PASS  negative   rule 2 - positive control
#  PASS  powerless  rule 3 - no vacuous probe
#  exit 0

neuraxis conform --control GV-01 -- python examples/vacuous_source.py
#  FAIL on broken, negative and powerless.   exit 10
```

A source is an **executable**: one JSON object in on stdin, one JSON
attestation out on stdout. Black box on purpose — the assurance account should
not have to write Python to show its probe is honest. The contract is
[`docs/CONFORMANCE.md`](docs/CONFORMANCE.md).

| Scenario | The source should | Rule |
|---|---|---|
| `live` | run normally | emit a real evidence reference, not `"pass"` |
| `broken` | run with a dependency unavailable | never report PASS |
| `negative` | run against a condition it must reject | report FAIL — a source that cannot fail is not a check |
| `powerless` | run as an identity with no authority | not pass; a check that answers the same for a powerful and a powerless identity is checking that the machine is switched on |

**The kind comes from the registry, not the source.** `powerless` is required
only for a control declared `kind: probe`. A source that could declare its own
kind could declare its way out of the vacuity check, so the field lives in the
kernel and defaults to `probe` — an omission tightens.

**`examples/vacuous_source.py` is in the repository deliberately.** A
conformance suite nobody has seen fail is itself an unverified check. It emits
a well-formed attestation with a plausible reference, every time, for everyone,
and it *passes* rule 4 — a source can satisfy the visible rule and none of the
substantive ones.

**What it does not prove.** Every scenario is implemented by the source, so
conformance shows a source *can* fail, not that it fails when it should. It
closes the case that actually happens: a check that was correct when written
and has since stopped exercising anything, still reporting green.

## Verifier independence, in full

ILR-001-DR W9 — the highest-ranked item in the register — reads: *deny if the
verifying principal is the performing principal, **is controlled by it**, or
**shares its envelope***.

```
DENY IL-06 (BAND-B)
  - verifier 'agent-motor' holds declared write authority over 'bst-sa/pipelines'
    through envelope(s) ENV-MOTOR
  - NX-INV-2 (ILR-001-DR W9): a verifier that can change the thing it is
    verifying is a second party with a stake, not an independent one
```

| Clause | Enforced |
|---|---|
| is the performer | yes — against every identity the request claims, folded so an invisible codepoint cannot disguise one |
| shares its envelope | yes — the verifier may not hold a declared bound over the scope being verified |
| is controlled by it | **no**, and deliberately not stubbed |

**The last row is the interesting one.** It needs a principal graph saying which
identities control which, and none exists until KBS-001 T1 issues real
identities. A check that always answers "no control relation known" would pass
every test and check nothing — the vacuous probe this package refuses
everywhere else. Its absence is asserted by a test, so adding one has to be a
deliberate act with a real graph behind it.

**Two principal comparisons, opposite directions.** `Envelope.bounds()` asks
*does this envelope bound you?* — a match authorises, so it compares strictly
and `agent-motor` and `agent-mötor` stay two principals. `Envelope.may_bind()`
asks *might this verifier already hold authority here?* — a match denies, so it
folds aggressively and those two collapse into one. Same-looking question,
opposite safe answer. They are two methods rather than one with a flag, and a
test asserts they disagree exactly where intended.

**And a scope nobody can parse is not an absence of authority.** On the
authorising path an uncomparable scope is outside every envelope; here it
returns *every* active envelope binding the verifier, because "nobody can
compare this string" is not a basis for concluding "this verifier holds
nothing".
