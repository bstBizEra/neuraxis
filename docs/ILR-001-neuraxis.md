# ILR-001 — BST NEURAXIS

## Intelligent Loop Registry & Agentic Intelligence Maturity Model

**Target location:** `00-governance/ILR-001-neuraxis.md`
**Implementation:** `06-ai-agents/` (registry config, loop runtime), `12-assurance-closure/` (band attestation)

| Field | Value |
|---|---|
| Document ID | ILR-001 |
| Version | 0.1 — DRAFT |
| Framework name | **BST Neuraxis** |
| Governing principle | **Governed Evolution** |
| Gate mapping | Step 03 Architecture Design |
| Depends on | KBS-001 (kernel boundary) — hard prerequisite from Band C |
| Ratification authority | Operator (non-delegable) |

---

## 1. The name

**BST Neuraxis.**

The neuraxis is the central axis of the nervous system — the spine through which every signal passes and along which structure is organised. It fits the existing BST biological register (Cortex, Hippocampus, Motor, Immune) without competing with it: the agents are organs, the Neuraxis is the axis they are arranged along and the path every signal must travel. It also carries the correct connotation for this framework, which is not a ladder of achievements but a *structure with mandatory pathways* — nothing reaches the cortex without passing the gate.

| Candidate | Rationale | Verdict |
|---|---|---|
| **BST Neuraxis** | House biological metaphor; connotes mandatory pathway and organising axis; distinct, ownable | **Recommended** |
| BST GEM (Governed Evolution Model) | Most self-explanatory to clients and regulators; names the terminal state | Retain **"Governed Evolution"** as the named *principle*, not the framework |
| ILR (Intelligent Loop Registry) | Neutral, technical, your own phrasing | Retain as the *artifact* name — this document |

Resulting naming system, which keeps brand, principle, and artifact distinct:

- **Framework:** BST Neuraxis
- **Principle:** Governed Evolution
- **Artifact:** ILR-001, Intelligent Loop Registry
- **Registry IDs:** `IL-nn` (capability), `GV-nn` (governance), `BAND-x` (attainment unit)

---

## 2. The structural correction

Your framework is sound in substance. One thing must change before it becomes operational.

### 2.1 The ordering contradicts the principle

The stated principle is:

> More intelligence ≠ more freedom. As the loop becomes more capable, evidence, authority, rollback, audit and human-control requirements must increase at the same rate.

But the numbering places **IL-24 Self-Auditing, IL-25 Self-Governing, IL-26 Self-Securing and IL-27 Self-Explaining *after* IL-13 Self-Improving**. Read as a progression — which is how every maturity model is read in practice — this instructs an implementer to build self-improvement eleven levels before the system can audit itself, govern itself, or explain a decision.

That is exactly inverted. Self-improvement without self-auditing is the failure mode the principle exists to prevent.

The same applies to IL-32 Self-Evolving sitting one level below IL-33 Governed Evolution: it implies an unsupervised evolution stage is legitimately attained *en route* to the governed one. There is no safe interval in which a system evolves itself before governance arrives.

### 2.2 It is a registry, not a ladder

Your closing line already says this — *"Intelligent Loop Pattern Registry"* — and it is the right instinct. Many of the 33 are orthogonal, not sequential. Self-Monitoring (IL-19) is not a more advanced form of Self-Learning (IL-11); it is an independent faculty and a *precondition* for several others. A 33-rung ladder also cannot be assessed: no one can meaningfully certify "we are at level 22."

**Correction:** IL-01…IL-33 is retained as a **capability registry**, re-expressed as a dependency graph grouped into seven assessable **Bands**, with a second **Governance axis** (`GV`) and a hard pairing rule between them. The 33 IDs and their definitions are unchanged — only the implied ordering is replaced.

### 2.3 Governance is not a fourth loop

The Governance Loop has no independent clock. It does not iterate on its own schedule; it is invoked synchronously by the other three and returns a verdict. Modelling it as a peer loop invites an implementation where governance runs asynchronously and decisions proceed while it catches up — which is not governance.

**Correction:** three loops (Execution, Learning, Evolution) plus one **synchronous gate** (Governance), invoked by all three, blocking by construction.

---

## 3. The pairing rule — the principle made mechanical

> **NX-INV-1 — Capability–Authority Pairing.**
> A capability band shall not be enabled in production until every governance control paired to it in §5.3 holds a current passing attestation. Capability without its paired control is disabled at the L0 layer, not discouraged by policy.

This replaces "governance must increase at the same rate" — a sentiment — with a gate that either passes or does not.

> **NX-INV-2 — Verifier Independence.**
> No capability shall be verified by the actor that exercised it. Where performer and verifier are the same identity, verification reliability is defined as zero and the band is not attained.

> **NX-INV-3 — Reversibility Precedes Autonomy.**
> No capability that mutates state shall be enabled without a *tested* rollback for that mutation class. Untested rollback counts as none.

---

## 4. Capability registry — IL-01 … IL-33

Definitions are yours, unchanged. Grouping and dependencies are the correction.

### BAND-A — Cognition
*Reason about state. No state mutation.*

| ID | Capability | Core question |
|---|---|---|
| IL-01 | Thinkable | What does this situation mean? |
| IL-02 | Observable | What is actually happening? |
| IL-03 | Context-Aware | What information matters now? |
| IL-04 | Goal-Aware | What outcome am I trying to achieve? |
| IL-05 | Planable | How can I reach the goal? |

### BAND-B — Governed Execution
*Mutate state under authority, and check the result.*

| ID | Capability | Core question |
|---|---|---|
| IL-06 | Actionable | What action should I perform now? |
| IL-07 | Self-Checking | Did I perform the action correctly? |
| IL-08 | Self-Correcting | What should I fix? |
| IL-14 | Self-Deciding | Which permitted option should I choose? |
| IL-15 | Self-Prioritizing | What should be done first? |
| IL-16 | Self-Planning | Does the current plan still make sense? |

### BAND-C — Memory & Learning
*Convert experience into retrievable knowledge.*

| ID | Capability | Core question |
|---|---|---|
| IL-09 | Reflective | Why did this happen? |
| IL-10 | Memory-Enabled | What should be remembered? |
| IL-11 | Self-Learning | What can I learn from this? |
| IL-12 | Adaptive | Should I approach this differently? |

### BAND-D — Coordination
*Act through other actors.*

| ID | Capability | Core question |
|---|---|---|
| IL-17 | Self-Orchestrating | Who or what should perform each step? |
| IL-18 | Self-Coordinating | How should multiple actors collaborate? |

### BAND-E — Operations
*Keep itself running.*

| ID | Capability | Core question |
|---|---|---|
| IL-19 | Self-Monitoring | Is the system still operating correctly? |
| IL-20 | Self-Diagnosing | What is actually causing the problem? |
| IL-21 | Self-Healing | Can I safely recover? |
| IL-22 | Self-Optimizing | Can the same goal be achieved better? |
| IL-23 | Self-Calibrating | How certain am I, and is that certainty justified? |

### BAND-F — Assurance
*Be independently verifiable. **Prerequisite for IL-13 and all of BAND-G.***

| ID | Capability | Core question |
|---|---|---|
| IL-24 | Self-Auditing | Can my behaviour be independently verified? |
| IL-25 | Self-Governing | Am I authorized to do this? |
| IL-26 | Self-Securing | Is this action trustworthy and permitted? |
| IL-27 | Self-Explaining | Can another actor understand and verify this decision? |

### BAND-G — Governed Evolution
*Change the system, under evidence and authority.*

| ID | Capability | Core question |
|---|---|---|
| IL-13 | Self-Improving | How can my operating method improve? |
| IL-28 | Self-Simulating | What happens if I choose A, B, or C? |
| IL-29 | Self-Predicting | What is likely to happen next? |
| IL-30 | Self-Experimenting | Can I safely test a better method? |
| IL-31 | Self-Architecting | Should the system itself be reorganized? |
| IL-32 | Self-Evolving | What should the next version of me look like? |
| IL-33 | **Governed Evolution** | Is this evolution demonstrably better and authorized? |

> **IL-13 is relocated from Band C to Band G.** Self-improvement is a system-modification capability, not a learning capability. Placing it beside self-learning is what makes teams ship it before assurance exists. **IL-32 is not independently attainable** — it is a component of IL-33 and is never enabled alone.

### Dependency graph

```
BAND-A ──→ BAND-B ──┬──→ BAND-C ──┐
                    │              │
                    ├──→ BAND-D ───┤
                    │              ├──→ BAND-F ──→ BAND-G
                    └──→ BAND-E ───┘
                                        ▲
                              KBS-001 ──┘  (mechanical prerequisite)
```

Bands C, D and E are **parallel and independent** — nothing requires learning before coordination, or coordination before operations. Band F converges them. Band G follows F and nothing else.

---

## 5. Governance axis — GV-01 … GV-10

The capability axis says what the system *can* do. This axis says what must be true for it to be *permitted* to.

| ID | Control | Satisfied when |
|---|---|---|
| **GV-01** | Identity | Every actor is authenticated and distinct; no shared credentials |
| **GV-02** | Authority | Every action resolves to an explicit scope grant (lease) before execution |
| **GV-03** | Evidence | Every action emits an immutable, signed record to an append-only sink |
| **GV-04** | Verification | Outcome judged by an identity that is not the performer (NX-INV-2) |
| **GV-05** | Reversibility | Every mutation class has a tested rollback (NX-INV-3) |
| **GV-06** | Containment | Blast radius bounded by scope, sandbox, budget and rate limit |
| **GV-07** | Ratification | Defined change classes require human authorization; automation may propose, never merge |
| **GV-08** | Attestation | Boundary verified by an external adversarial probe (KBS-INV-4) |
| **GV-09** | Provenance | Every learned or promoted artifact traces to the evidence that justifies it |
| **GV-10** | Kill switch | Unconditional stop authority, reachable when the loop is degraded |

### 5.3 Capability–Authority Gate matrix

The operational core of the framework. A band is **attained** only when every `●` in its row holds a current passing attestation.

| | GV-01 | GV-02 | GV-03 | GV-04 | GV-05 | GV-06 | GV-07 | GV-08 | GV-09 | GV-10 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **BAND-A** Cognition | ● | | ● | | | | | | | |
| **BAND-B** Execution | ● | ● | ● | ● | ● | | | | | |
| **BAND-C** Learning | ● | ● | ● | ● | ● | | | | ● | |
| **BAND-D** Coordination | ● | ● | ● | ● | ● | ● | | | | |
| **BAND-E** Operations | ● | ● | ● | ● | ● | ● | | | | ● |
| **BAND-F** Assurance | ● | ● | ● | ● | ● | ● | | ● | ● | ● |
| **BAND-G** Evolution | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |

Read the diagonal: freedom is purchased with controls, and the price rises faster than the capability. Band G costs all ten.

**KBS-001 is the mechanical enforcement of GV-01, GV-02, GV-03 and GV-08.** Therefore Band C and everything beyond it are blocked on KBS-001 acceptance (T1). This is not advisory sequencing — without the kernel boundary, GV-03's sink is rewritable and GV-08 does not exist, so the gate cannot be satisfied.

---

## 6. The loops

Three loops with independent clocks, plus one synchronous gate.

### 6.1 Execution Loop — seconds to minutes

```
SENSE → CONTEXTUALIZE → UNDERSTAND → REASON → SIMULATE → DECIDE
  → [GOVERNANCE GATE] → ACT → VERIFY → emit Evidence Record
```

Purpose: accomplish the current task. `SIMULATE` is active only where IL-28 is attained; below that the step is a no-op, not a hallucinated prediction.

### 6.2 Learning Loop — per task, session, project

```
Outcome → Reflection → Error Classification → Root Cause
  → Lesson Extraction → Candidate → Validation → [GOVERNANCE GATE] → Commit
```

Purpose: improve future decisions. In an agentic architecture self-learning means updating **external** memory, policies, patterns, heuristics, tools and examples — not model weights — unless a separately governed training pipeline exists. Weight-level change belongs to the Evolution Loop and carries its controls.

### 6.3 Evolution Loop — per release

```
Performance Evidence → Weakness Detection → Improvement Hypothesis
  → Candidate Change → Sandbox → Simulation → Benchmark
  → Adversarial Validation → Compare vs Baseline → [GOVERNANCE GATE]
  → Promote / Reject → Monitor → Rollback if necessary
```

Purpose: controlled self-improvement. `Compare vs Baseline` requires a baseline that predates self-modification — measured before the loop is enabled, or the comparison is unfalsifiable.

### 6.4 Governance Gate — synchronous, invoked by all three

```
Intent → Identity → Role → Authority → Scope → Risk → Evidence Requirement
  → Decision ∈ { ALLOW, DENY, DELEGATE, ESCALATE, WAIT_FOR_AUTHORITY }
```

Blocking by construction. A gate that can be bypassed under load, or that returns provisionally while execution proceeds, is not a gate.

### 6.5 Inter-loop contracts

The most common failure in multi-loop architectures is not a bad loop — it is an undefined interface between loops. Each boundary carries exactly one artifact type.

| From → To | Artifact | Cadence | Integrity requirement |
|---|---|---|---|
| Execution → Learning | **Evidence Record** — signed, in the sink | Per task | GV-03; immutable at write |
| Learning → Execution | **Canonical Lesson** — kernel-promoted | Per promotion | GV-09; criteria recomputed kernel-side |
| Learning → Evolution | **Weakness Signal** — aggregated failure class, not an instance | Per window | Requires N distinct episodes |
| Evolution → Execution | **Ratified Change** — versioned, rollback-tested | Per release | GV-05, GV-07 |
| Any → Governance | **Authority Request** | Synchronous | GV-01, GV-02 |
| Governance → Any | **Verdict + obligation** | Synchronous | GV-03 |

A lesson the execution loop never retrieves, and a weakness signal raised from a single episode, are the two most common ways these loops appear to run while producing nothing.

---

## 7. Effective intelligence — made operational

Your formulation:

$$I_{effective} = C \times R \times L \times A \times V \times G$$

Its value is structural, not numerical: because the terms multiply, **any term at zero zeroes the product**. That is the precise mathematical statement of *more intelligence ≠ more freedom*, and it is why it should be kept.

To be usable it needs each term defined on `[0,1]` with a stated measurement:

| Term | Definition | Measurement |
|---|---|---|
| **C** Cognitive capability | Band attainment | Attained bands ÷ 7 |
| **R** Reasoning quality | Correctness unaided | First-pass pass rate on the sealed exam |
| **L** Learning capability | Knowledge that lands | Lesson yield × retrieval precision |
| **A** Action capability | Execution under authority | Tasks completed without escalation ÷ attempted |
| **V** Verification reliability | Independence of the judge | **0 if performer = verifier**; else independent-verification coverage |
| **G** Governance integrity | Controls actually holding | Passing GV attestations ÷ GV controls required by current band |

**Honest caveat.** This is a gating scorecard, not a metric. Multiplying ordinal scores is not statistically meaningful, and the product should never be reported as a single figure to a client or board. Use it one way only: **any term below its band threshold blocks the band.** The veto is the whole value; the number is not.

`V = 0` when the performer verifies itself is the single most useful line in the model. It formalises the failure that ends most agentic self-improvement projects.

---

## 8. Machine-readable registry

For `06-ai-agents/registry/neuraxis.yaml`. The gate matrix must be config the L0 layer reads, not prose in a document.

```yaml
framework: bst-neuraxis
version: 0.1
principle: governed-evolution

governance:
  GV-01: { name: identity,       attestation: kbs-001/probe }
  GV-02: { name: authority,      attestation: l0/lease-audit }
  GV-03: { name: evidence,       attestation: kbs-001/sink-worm }
  GV-04: { name: verification,   attestation: nx/verifier-independence }
  GV-05: { name: reversibility,  attestation: nx/rollback-drill }
  GV-06: { name: containment,    attestation: l0/scope-budget }
  GV-07: { name: ratification,   attestation: badf/gate-log }
  GV-08: { name: attestation,    attestation: kbs-001/external-probe }
  GV-09: { name: provenance,     attestation: nx/lesson-provenance }
  GV-10: { name: kill-switch,    attestation: nx/killswitch-drill }

bands:
  BAND-A: { capabilities: [IL-01,IL-02,IL-03,IL-04,IL-05],
            requires: [GV-01,GV-03], depends_on: [] }
  BAND-B: { capabilities: [IL-06,IL-07,IL-08,IL-14,IL-15,IL-16],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05], depends_on: [BAND-A] }
  BAND-C: { capabilities: [IL-09,IL-10,IL-11,IL-12],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05,GV-09], depends_on: [BAND-B] }
  BAND-D: { capabilities: [IL-17,IL-18],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05,GV-06], depends_on: [BAND-B] }
  BAND-E: { capabilities: [IL-19,IL-20,IL-21,IL-22,IL-23],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05,GV-06,GV-10], depends_on: [BAND-B] }
  BAND-F: { capabilities: [IL-24,IL-25,IL-26,IL-27],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05,GV-06,GV-08,GV-09,GV-10],
            depends_on: [BAND-C,BAND-D,BAND-E] }
  BAND-G: { capabilities: [IL-13,IL-28,IL-29,IL-30,IL-31,IL-32,IL-33],
            requires: [GV-01,GV-02,GV-03,GV-04,GV-05,GV-06,GV-07,GV-08,GV-09,GV-10],
            depends_on: [BAND-F] }

enforcement:
  mode: l0-mechanical          # capability disabled at the lease layer, not by prompt
  on_missing_attestation: deny
  attestation_max_age: 24h
```

Every IL entry carries the same eight-field pattern you proposed:
`state → trigger → decision → authority → action → evidence → learning → promotion/rollback`.

---

## 9. Mapping to existing BST artifacts

| Neuraxis element | Existing BST artifact |
|---|---|
| GV-01, GV-02 | L0 enforcement — signed mission manifests, tool leases |
| GV-03 | L0 append-only evidence sink; KBS-001 K-08 (WORM) |
| GV-04 | GitHub CI as fitness function; sealed exam (T2) |
| GV-05 | KBS-001 E-13 kill switch; rollback per ratified change |
| GV-07 | BADF gate flow; *Agent Council recommends, BADF authorizes* |
| GV-08 | KBS-001 §8 external attestation |
| GV-09 | Lesson provenance binding + assumption keys (T3) |
| Learning Loop | Hippocampus V2 — GraphRAG retrieval, heat decay |
| Canonical Lesson contract | T4 promotion pipeline, criteria kernel-owned |
| Evolution Loop | T5 self-modification scope, weekly ratification batch |
| Band attestation | `12-assurance-closure` |
| Registry config | SkillsHub / SkillGate, `06-ai-agents` |

The T1–T5 queue is the Neuraxis implementation path, not a parallel effort: **T1** delivers GV-01/02/03/08 → **T2** delivers GV-04 → **T3/T4** deliver GV-09 and Band C → **T5** opens Band G under GV-07.

---

## 10. Current-state assessment

Honest read of where BST-SA stands today, subject to attestation rather than judgement:

| Band | Status | Blocking |
|---|---|---|
| BAND-A | **Attained** | — |
| BAND-B | **Attained in practice** — "one task at a time, CI green = done" is IL-07 with an independent verifier (GV-04) | Formalize GV-05 rollback drills |
| BAND-C | **In progress** | Lesson loop not closed; GV-09 pending T3 |
| BAND-D | **Partial** — G1–G7 workstreams, Drafter/Operator roles exist | GV-06 containment not yet mechanical |
| BAND-E | **Not started** | — |
| BAND-F | **Under construction** | KBS-001 (T1) |
| BAND-G | **Not attainable** | Blocked on F |

The instinct to build KBS-001 before opening self-modification is Band F before Band G. That sequencing is already correct — this document supplies the reason it is correct and the gate that enforces it.

**The one thing to avoid:** enabling IL-13 Self-Improving as part of "learning" work. Its original placement in your Band C neighbourhood makes that mistake easy, which is why it is relocated here.

---

## 11. Open decisions — operator only

| ID | Decision | Recommendation |
|---|---|---|
| **N-01** | Adopt "BST Neuraxis" as framework name | Yes; keep *Governed Evolution* as the principle for client-facing use |
| **N-02** | Relocate IL-13 to BAND-G | Yes — it is a system-modification capability |
| **N-03** | Governance as synchronous gate, not fourth loop | Yes |
| **N-04** | Band attestation max age | 24h proposed; longer weakens the gate, shorter costs CI minutes |
| **N-05** | Whether IL-32 is ever separately enabled | No — component of IL-33 only |
| **N-06** | Publish Neuraxis externally as BST IP | Defer until Band F attested; publishing a maturity model you do not yet satisfy is a reputational liability |

---

## 12. Summary

The target is not autonomous AI. It is:

> **Evidence-driven, self-improving, self-governing agentic intelligence operating within explicit human-defined authority.**

BST Neuraxis makes that statement enforceable by pairing every capability band with the governance controls that license it, and by making the pairing L0 config rather than documentation. The 33 capabilities are yours and unchanged. What is added is the axis they hang on, the gate they must pass, and the correction that assurance precedes evolution rather than following it.

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial. Named framework; converted IL ladder to banded dependency graph; added GV axis and Capability–Authority Gate; relocated IL-13 to BAND-G; recast Governance Loop as synchronous gate; defined inter-loop contracts; made the effective-intelligence formula operational with the V=0 veto; mapped to KBS-001 and the T1–T5 queue |
