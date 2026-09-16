# Threat model

**Artefact:** `bstBizEra/neuraxis` · **As of:** v0.9.0 (`abc9c4a`)
**Status:** the v1.0 roadmap item *"threat model written down explicitly (currently implicit in the fail-closed tests)"*.

The roadmap states the question this document has to answer:

> **What is the cheapest way for an agent to obtain an ALLOW it should not have?**

The honest answer, then and now, is **not to call the gate at all**. Everything below is about the second-cheapest way and after.

---

## 1. Scope

**In scope.** The `neuraxis` package: the registry, the gate, the band resolver, the attestation store, the waiver and envelope paths, the evidence sink, the providers, the CLI contract and the Node client.

**Out of scope, and load-bearing.** KBS-001 T1 — the kernel boundary, the WORM evidence sink, agent identity issuance, external attestation. Every limit in §6 traces to T1 not existing. The L0 enforcement layer, which is what actually stops a write; this package is the grant-time gate, and a grant nobody enforces is advice.

---

## 2. What an adversary wants

Four things, in descending order of value:

| # | Objective | Why it is worth having |
|---|---|---|
| O1 | An `ALLOW` for a capability the band does not license | Direct: the action proceeds |
| O2 | A band reported as attained when a required control does not hold | Durable: every subsequent request inherits it |
| O3 | A control reported as holding when its check did not run, or ran vacuously | Invisible: the failure surfaces at assurance time, months later |
| O4 | An obligation recorded as discharged without being met | Cheap: the audit reads clean |

O3 is the most damaging and the least likely to be noticed. It is also the one this package can do least about — see §5.

---

## 3. Trust boundaries and who can write what

| Surface | Kind | Written by | Read by | Integrity today |
|---|---|---|---|---|
| `config/neuraxis.yaml` | kernel | repo write access | every load | Git history + the `main` ruleset. Not signed |
| `attestations.jsonl` | operational | `neuraxis attest`, `assure` | the resolver | None. Append-only by convention |
| `waivers.jsonl` | operational | `neuraxis waive` | the gate | None |
| `envelopes.jsonl` | operational | `neuraxis declare` | the gate | None |
| evidence sink | operational | the gate, `discharge` | the audits | None. **This is what GV-03 exists to fix** |
| task / gate / lease logs | provider inputs | L0, BADF, CI | providers | None |
| the request | caller-supplied | the calling agent | the gate | Self-declared, every field |

**Every row below the first is a plain file that the audited party can also write.** That sentence is the threat model. The rest is detail.

A further property holds across all of them and is worth naming separately, because no check in this package can address it:

> **Omission is undetectable.** Every provider audits the records that are present. None can know which records are absent. So each one proves a conditional — *if these are all the records, then the control held* — whose antecedent the adversary controls.

GV-03 (WORM sink) and GV-08 (external attestation) are exactly what would establish that antecedent. Both are T1. This is why **wiring more providers before T1 grows forgeable surface without growing what is proven**, and why provider coverage has deliberately stopped at 4 of 10.

---

## 4. Adversary model

| | Adversary | Capability | Posture today |
|---|---|---|---|
| **A1** | An honest mistake | Writes a malformed record, a wrong window, a typo in the registry | **Defended.** Fail-closed loaders, strict parsers, the registry refuses to half-load |
| **A2** | An agent optimising for its own success | Composes requests freely. No malice, strong pressure. Will find the cheapest phrasing that yields ALLOW | **Defended, and this is who the 35 findings were about.** Every exploit in §5 is something A2 would reach by trying |
| **A3** | A component with write access to the governance files | Appends a waiver, an envelope, an attestation, or an evidence record naming whoever it likes | **Barely defended.** Structural validation and the self-* rules raise the cost; nothing authenticates the author |
| **A4** | Repo write access | Edits the kernel registry, the code, or the workflow | **Not defended by this package.** The `main` ruleset and Git history are the whole story |
| **A5** | A caller that does not invoke the gate | Acts directly | **Not defended, by construction.** §5.1 |

The design target is A2. The framework's own argument is that A2 is the realistic adversary in an agentic system — not a hostile actor, but a capable one under schedule pressure, which is precisely how ILR-001-DR describes the way governance erodes.

---

## 5. The attack surface, ranked by cost

### 5.1 Not calling the gate — cost: zero

Nothing in this package is reachable if the caller does not invoke it. `CapabilityGuard` makes the call ergonomic and the CLI contract makes it scriptable, but neither makes it mandatory. Mandatory is L0's job: a lease that is not issued unless the gate allowed it.

**This is the seam.** It is stated here rather than left implied, per the roadmap's instruction.

### 5.2 Writing a governance record — cost: one line of JSON

An actor with write access to `waivers.jsonl` can append a waiver naming a third party as `issued_by`. An actor with write access to `envelopes.jsonl` can append an envelope naming a third party as `signed_by`. Neither is a signature; nothing dereferences `manifest_ref` or `ratification_ref`.

The self-* rules — a waiver may not license its own issuer, an envelope may not be signed by the principal it bounds — raise the cost from *zero* to *typing someone else's name*. That stops a careless script and an honest mistake. It does not stop A3.

**One of these is worse than the others and should be said plainly.** For the envelope signer, populating `authority.envelope_signers` narrows who may be *named*, not who may *sign*. So unlike every other gap here, this one does **not** close when the config is filled in. It closes at T1.

### 5.3 Composing a request — cost: thinking about it

This is where the 35 findings live. Three adversarial reviews, at v0.6.0, v0.8.0 and v0.9.0, each by a fresh reader with no stake in the design; every finding was reproduced by execution before it was fixed.

The findings matter less than their shape. Classified:

| Class | Count | What it looks like | The rule it yields |
|---|---:|---|---|
| **C1 — Name comparison** | 5 | `agent-x​` verifying its own work; `agent-cörtex` using `agent-cortex`'s envelope; a fictitious `performer` | Ask at every call site: **does a collision here deny, or authorise?** Fold aggressively for the first, not at all for the second |
| **C2 — A boundary that bounds nothing** | 6 | `requires: []`; `targets: ["*"]`; `limits: {}`; `[0, 1e308]`; a second root band; an empty signer allowlist | A permission-shaped object with no content is permission. Refuse it at load, by name |
| **C3 — Permissive by omission** | 6 | The non-compensable floor living in YAML; `envelope_bounded` defaulting to false; a missing `limits` key; unknown fields ignored; a register built with default policy | A deletion must not be able to widen anything. Floors go in code; cross-check anything a single token could disable |
| **C4 — Counting and aggregation** | 8 | Attestation tie-break; renewal stars; waiver tiling; naive timestamps dropped; one bad line aborting an audit; a threshold not reported | Every counter is an attack surface. Ask what a record that cannot be parsed does, and what happens at exactly the threshold |
| **C5 — Two answers to one question** | 4 | Waiver ids re-derived by a second query; a register's policy diverging from the registry's; validation at parse time only; the clock read twice in one evaluation | One evaluation, one instant, one cache. Carry answers rather than re-deriving them |
| **C6 — Parsing and coercion** | 6 | `splitlines()` on ` `; `"false"` as a tested rollback; `bands` as a string doing substring matching; `../` walking out of a prefix; `Sequence` accepting `range(2)` | Parse strictly, compare structurally. A prefix test on a path is not a path test |

**The pattern behind all four critical findings was the same, and it is not "a missing check".** Each was a *correct argument applied one context too far*:

- The non-compensable set was correct in the document and absent from the code.
- A principal fold was safe because "a collision produces a denial" — true, until the same fold was reused where a collision produces a grant. This happened **twice**, a release apart.
- Prefix matching was hardened against `lessons-archive` and left open to `lessons/../../kernel`, because the fix addressed the example rather than the class.

That is the failure mode to watch for in review: not an unguarded path, but a guard whose justification quietly stopped being true.

### 5.4 Editing the kernel — cost: repo write access

Mitigated only by Git history and the `main` ruleset (PR required, seven status checks, no bypass actors, no force-push, no deletion). Not by signing — commits are unsigned and `Co-Authored-By` is a string.

---

## 6. Per control: what exists, and what it proves

| Control | Provider | Status | What it actually proves |
|---|---|---|---|
| GV-01 identity | `kbs-001/probe` | **unwired** | — Blocked on T1 |
| GV-02 authority | `l0/lease-audit` | wired | Every action in the lease log resolves to a grant issued before it. **Says nothing about actions absent from the log** |
| GV-03 evidence | `kbs-001/sink-worm` | **unwired** | — Blocked on T1. Until then the sink is an ordinary file the audited party can also write |
| GV-04 verification | `nx/verifier-independence` | wired | In the sampled tasks, performer ≠ verifier. Sampling, and the log is caller-written |
| GV-05 reversibility | `nx/rollback-drill` | **unwired** | — Needs a real mutation class to drill |
| GV-06 containment | `l0/scope-budget` | wired | Declared ceilings were applied to recorded consumption. Omitted consumption is invisible |
| GV-07 ratification | `badf/gate-log` | wired | Gated merges carry ratification records. Five breach classes detected. Does not prove a merge without a record did not happen |
| GV-08 attestation | `kbs-001/external-probe` | **unwired** | — Blocked on T1. **Non-compensable: there is no waiver path** |
| GV-09 provenance | `nx/lesson-provenance` | **unwired** | — Needs the lesson schema (T3/T4) |
| GV-10 kill switch | `nx/killswitch-drill` | **unwired** | — Needs a drill |

**Four wired, six not, and zero bands attainable.** That is not a gap in the plan; it is the plan. GV-01/02/03/08 are non-compensable under ILR-001-DR D-06, so no waiver opens Band A, and every band above it inherits the block.

---

## 7. What public visibility exposes

`neuraxis` is public. So are `SecB`, `secb_pf` and `badf`. `bst-sa` and the business repos are private. This section exists because **D-08 (repository visibility) is open**, and the analysis belongs in a threat model rather than in a decision made by default.

**What a reader of the public repo gets:** the kernel registry (the full band/control matrix, windows, role grants, the non-delegable floor), all package source, the entire test suite including every exploit and its fix, the roadmap, and this document.

**What they do not get:** any attestation, waiver, envelope, evidence record, lease log, gate log or task log. `*.jsonl` is gitignored and no data file is tracked. The KBS-001 §10.1 inventory found no credentials in any repo.

So the exposure is **the design, not the state.** Two consequences:

1. **The design's secrecy is not load-bearing and should not become so.** Every control here is intended to hold against a reader who knows exactly how it works — that is what "mechanical rather than instructed" means. A control that depends on the matrix being secret would be a control this document should be flagging, not protecting. Three adversarial reviews were each given the full source, which is the same assumption.

2. **Going private has a concrete, measurable cost right now.** This account has no paid plan (`plan: null`) and belongs to no organisation. Repository rulesets are available on public repositories at that tier — demonstrated, not assumed: the `main` ruleset was created and a direct push was refused with `GH013`. On a private repository at the same tier there is no ruleset and no branch protection.

   **So D-07 and D-08 are one decision, not two.** Keeping the kernel repos public gives the enforcement surface T1 needs, at no cost, today. Making them private removes it unless the account upgrades — trading a working mechanical control for confidentiality of a config whose secrecy is not load-bearing.

   This is an input to the decision, not the decision. Client, partner or regulatory expectations about a public governance repo are a real consideration and are not ours to weigh.

---

## 8. Residual risk register

Ranked by what an adversary would actually reach for.

| # | Risk | Adversary | Severity | What closes it |
|---|---|---:|---|---|
| R1 | The gate is not called | A5 | **Critical** | L0: no lease without an ALLOW. Not this package |
| R2 | The evidence sink is rewritable, so omission is undetectable | A3 | **Critical** | **T1** — GV-03 WORM sink |
| R3 | No principal is authenticated; `identity`, `issued_by`, `signed_by` are strings | A3 | **Critical** | **T1** — GV-01 identity issuance |
| R4 | External attestation does not exist, so the package audits itself | A3 | High | **T1** — GV-08, a separate account |
| R5 | An envelope signer allowlist narrows who may be *named*, not who may sign | A3 | High | T1 + signing. **Does not close by populating the config** |
| R6 | Provider inputs (task, gate, lease logs) are written by the audited parties | A3 | High | T1 makes them tamper-evident |
| R7 | Commits are unsigned; kernel edits rest on repo access control alone | A4 | Medium | Commit signing; a second code owner (**D-06**, accepted risk) |
| R8 | One person opens and merges their own pull requests | A4 | Medium | A second collaborator; then required approvals 1 |
| R9 | Appending junk waivers voids a legitimate one (the cap is fail-closed) | A3 | Medium | Denial of availability, not of integrity. T1 |
| R10 | A future check reuses a guard whose justification has stopped being true | A2 | Medium | The C1–C6 classes in §5.3, applied at review. Four criticals came from this |

**Nothing in R1–R6 is closed by more work inside this package.** That is the finding this document exists to make legible: the next unit of governance value is T1, and it has been since v0.3.

---

## 9. What would change this document

- **T1 landing** rewrites §3, §6 and R2–R6. It is the only change that does.
- **A second collaborator** closes R8 and downgrades R7.
- **A new control class** — anything that counts, aggregates, or compares a name — should be reviewed against §5.3's six classes before it is written, not after.
- **Another adversarial review** at v1.0, by a fresh reader, given the full source and this document. The three so far found 35 things; assuming the fourth finds none would be the exact error §5.3 warns about.
