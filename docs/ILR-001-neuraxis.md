# ILR-001 — BST NEURAXIS

## Intelligent Loop Registry & Agentic Intelligence Maturity Model

**Target location:** `00-governance/ILR-001-neuraxis.md`
**Implementation:** `06-ai-agents/` (registry config, loop runtime), `12-assurance-closure/` (band attestation)

| Field | Value |
|---|---|
| Document ID | ILR-001 |
| Version | **0.2** — amended against ILR-001-DR |
| Framework name | **BST Neuraxis** |
| Governing principle | **Governed Evolution** |
| Gate mapping | Step 03 Architecture Design |
| Depends on | KBS-001 (kernel boundary) — hard prerequisite from Band C |
| Ratification authority | Operator (non-delegable) |
| Amended by | ILR-001-DR Rev A (D-01…D-06) and its D-07 addendum |
| Enforced by | `bstBizEra/neuraxis` — the registry, gate and CLI |

> **v0.1 was a draft written before the decisions.** ILR-001-DR ruled on six
> structural questions and amended four of them; a seventh was added when the
> L0 integration shape was settled. Everything built since has been built
> against the register, not against this document, so four sections of v0.1 now
> describe a framework that is not the one running. §13 lists each change and
> the ruling that made it.
>
> **Where this document and the register disagree, the register is normative
> and this document is the bug.** Where this document and the shipped registry
> disagree, a test fails — see §8.

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

### 2.4 What the register changed after this section was written

§2.1–2.3 were right about the problems and, in two places, wrong about the
remedies. The register scored the alternatives and ruled:

| v0.1 said | ILR-001-DR ruled | Why |
|---|---|---|
| Relocate **all** of IL-13 to Band G | **Split** it: IL-13a Self-Tuning (Band C, envelope-bounded), IL-13b Self-Modifying (Band G) — **D-01** | The wholesale move is right in principle and loses in practice. Teams adjust thresholds, retry budgets and routing weights as ordinary work; a rule forbidding it gets reclassified as "configuration" and done out of view. An unenforceable prohibition is worse than none |
| The gate is **synchronous, invoked by all three loops** | Synchronous **at authority-grant**; asynchronous **revoke-only** within a granted envelope — **D-03** | Gating every action collapses throughput, and a team whose throughput has collapsed builds an emergency bypass that becomes the normal path within a quarter |
| Keep the formula, operational, with a caveat | **Retire it to non-normative.** §7 becomes a boolean precondition set — **D-04** | A formula whose only valid reading is a boolean AND invites the board slide the caveat forbids |
| *(not addressed)* | Waivers must carry a named accountable, a compensating control and a **hard expiry** — **D-05** | An exception path with no expiry is how a temporary gap becomes the permanent architecture |
| *(not addressed)* | GV-01/02/03/08 are **non-compensable** — no waiver path at all — **D-06** | An append-only sink a human promises not to rewrite is a rewritable sink |
| *(not addressed)* | L0 reaches the gate by **shelling out to the CLI**, and must prove it with a conformance suite — **D-07** | The cheapest integration, and the one that moves the whole enforcement burden across a process boundary |

The two corrections in §2.1 and §2.2 stand unchanged and are the reason the
framework works at all. §2.3's diagnosis stands; its remedy was too strong.

---

## 3. The pairing rule — the principle made mechanical

> **NX-INV-1 — Capability–Authority Pairing.**
> A capability band shall not be enabled in production until every governance control paired to it in §5.3 holds a current passing attestation. Capability without its paired control is disabled at the L0 layer, not discouraged by policy.

This replaces "governance must increase at the same rate" — a sentiment — with a gate that either passes or does not.

> **NX-INV-2 — Verifier Independence.**
> No capability shall be verified by the actor that exercised it. Where performer and verifier are the same identity, verification reliability is defined as zero and the band is not attained.

> **NX-INV-3 — Reversibility Precedes Autonomy.**
> No capability that mutates state shall be enabled without a *tested* rollback for that mutation class. Untested rollback counts as none.

> **NX-INV-4 — Non-compensable integrity controls.**
> GV-01, GV-02, GV-03 and GV-08 admit no waiver, no named-accountable path and
> no expiry path. See §5.5.

> **NX-INV-5 — Monotonic control sets.**
> Each band's required control set is a superset of every band it depends on.
> See §5.4.

NX-INV-2 has three clauses and two of them are enforced: a verifier may not be
an identity the request claims, and may not hold declared write authority over
the scope it is verifying. The third — *a verifier controlled by the performer*
— is deliberately absent; see §13.

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
| **IL-13a** | **Self-Tuning** | Can I adjust my own parameters inside a declared bound? |

> **IL-13a is admissible here, and only inside an envelope** (ILR-001-DR D-01).
> The envelope is declared in advance, machine-evaluable, and signed by someone
> other than the component it bounds. The gate denies unless the request names
> an envelope that is active, bounds every identity the request claims, covers
> the write target component-by-component, and contains every declared
> adjustment inside a finite interval. A bound that is not a finite interval is
> not a bound: `[0, 1e308]` is the infinity bypass with more zeroes.

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
| **IL-13b** | **Self-Modifying** | How can my operating method improve? |
| IL-28 | Self-Simulating | What happens if I choose A, B, or C? |
| IL-29 | Self-Predicting | What is likely to happen next? |
| IL-30 | Self-Experimenting | Can I safely test a better method? |
| IL-31 | Self-Architecting | Should the system itself be reorganized? |
| IL-32 | Self-Evolving | What should the next version of me look like? |
| IL-33 | **Governed Evolution** | Is this evolution demonstrably better and authorized? |

> **IL-13 is split, not relocated** (ILR-001-DR D-01, amending v0.1 of this
> document). Self-modification is a system-modification capability and belongs
> here. Parameter tuning inside a declared bound is not, and a framework that
> pretends otherwise gets the tuning done outside it. The line between them is
> drawn **mechanically rather than by intent**: IL-13a is whatever fits inside
> a signed, finite, machine-evaluable envelope, and IL-13b is everything else.
> A request for an envelope-bounded capability that names no envelope is IL-13b
> wearing IL-13a's name, and is denied.
>
> **IL-32 is not independently attainable** — it is a component of IL-33 and is
> never enabled alone. There is no safe interval in which a system evolves
> itself before governance arrives.

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

> **Prohibited in any contract, proposal, marketing asset or regulatory filing**
> (ILR-001-DR D-02): ordinal attainment claims.
> <!-- prohibited-examples -->
> Not *"BST operates at IL-22"*, not *"level 22 of 33"*.
> <!-- /prohibited-examples -->
> The permitted form is **"Bands A and B attained; Band C in progress"**, with
> the attestation reference. The IL index is published
> for orientation only and is **non-normative**; the graph above is the
> normative structure, and bands are the only unit that can be attested.
>
> The ordinal-claim test skips the fenced region above and asserts there is
> exactly one such fence, so this exemption cannot be widened quietly.
>
> This is a communications control, not an L0 control — it belongs in the comms
> review checklist, and it is the cheapest credibility protection in the
> framework. **Reversal trigger:** an external party cites an ordinal level back
> to BST in writing. That means the index is being read as normative and it gets
> pulled.

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

**The block derives from the matrix; it is not a separate clause** (D-06).
Band C requires GV-01/02/03/08, T1 is their mechanical implementation,
therefore Band C is blocked until T1 lands. One rule instead of two, and it
generalises: any future band inherits its blockers from its control set
automatically.

### 5.4 Monotonicity

> **NX-INV-5 — Monotonic control sets.**
> Each band's required control set is a superset of every band it depends on.

Read the matrix again: no `●` is ever removed as you go down. This is asserted
at registry load, not written in prose, because a non-monotonic mapping means
some transition *reduces* required controls — which is unauditable, and worse,
creates an incentive to declare a higher band in order to escape a control.

### 5.5 The exception path

Real programmes need one, and an exception path with no expiry is how a
temporary control gap becomes the permanent architecture. D-05 fixes its shape.

Every waiver carries: **the specific GV control waived, a named accountable
person, a compensating control, a hard expiry, and an entry in the evidence
sink.** On expiry the gate denies automatically; renewal re-enters the
synchronous path. No standing waivers, no waiver-by-default, no silent
rollover. A waiver never licenses its own issuer or the principal accountable
for it.

Three bounds are **constants in the enforcing code, not settings in the
registry**, because a bound that exists to constrain the registry cannot live
in it: a 90-day TTL ceiling, at most two active waivers, and at most one
renewal. A registry may tighten any of them and may never loosen one.

**And four controls have no waiver path at all** (D-06):

> **NX-INV-4 — Non-compensable integrity controls.**
> GV-01, GV-02, GV-03 and GV-08 admit no waiver, no named-accountable path and
> no expiry path.

They are integrity controls, and integrity controls are not compensable by
human process:

- An append-only evidence sink that a human promises not to rewrite is a
  rewritable evidence sink.
- External attestation performed by an internal party is not external
  attestation.
- A kernel boundary enforced by convention is a convention.

The failure is silent. Nothing breaks when a human compensating control
degrades; the evidence just quietly stops being evidence, and it is discovered
at the assurance stage, when Band F tries to use records that cannot be shown to
be unaltered. **This is the compounding cost:** evidence written before the
immutable sink exists cannot be retroactively attested. It is not delayed value,
it is permanently unusable value, and it accrues every week T1 slips.

**Reversal trigger for the waiver path:** any waiver renewed twice, or more than
two active at once. Either says the matrix is mis-calibrated against what BST
can actually build, and the honest response is to re-cut the matrix — not to
keep waiving it.

---

## 6. The loops

Three loops with independent clocks, plus one synchronous gate.

### 6.1 Execution Loop — seconds to minutes

```
SENSE → CONTEXTUALIZE → UNDERSTAND → REASON → SIMULATE → DECIDE
  → ACT → VERIFY → emit Evidence Record
```

Purpose: accomplish the current task. `SIMULATE` is active only where IL-28 is attained; below that the step is a no-op, not a hallucinated prediction.

> **The gate is not a step in this loop** (D-03, amending v0.1 of this
> document). v0.1 drew `[GOVERNANCE GATE]` between DECIDE and ACT, which reads
> as *every action blocks on governance* — the option D-03 scored and rejected.
> A task executing inside an already-granted lease does **not** call the gate;
> it proceeds at full speed, and the audit stream observes it. The gate fires
> when what the component is *allowed* to do changes. See §6.4.

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

### 6.4 Governance Gate — synchronous at authority-grant

```
Intent → Identity → Role → Authority → Scope → Risk → Evidence Requirement
  → Decision ∈ { ALLOW, DENY, DELEGATE, ESCALATE, WAIT_FOR_AUTHORITY }
```

Blocking by construction. A gate that can be bypassed under load, or that
returns provisionally while execution proceeds, is not a gate.

**It fires on five events and no others** (D-03):

```
lease_issue · lease_widen · band_transition · envelope_amend · verifier_assign
```

Every one of them is a change to what a component is *allowed* to do. Nothing
else blocks. **`lease_widen` is the one that gets missed**: a widening is a
fresh grant of authority arriving through a code path that already holds a
valid lease, which is exactly why it feels like it does not need asking.

**Within a granted envelope the audit stream is asynchronous and revoke-only.**
It observes and appends to the evidence sink. It **cannot approve anything**;
its only authority is to revoke or to let a lease expire. That is what keeps it
from becoming a fourth loop: no grant authority, and no independent clock over
authority. Leases are fail-closed and time-boxed, so the async path never needs
to act in order for authority to lapse.

> **Reversal trigger:** a bypass path is created around the gate, *or* median
> lease TTL drifts upward across two consecutive reviews. Rising TTL is a
> bypass in disguise — the team routing around latency by asking for longer
> grants.

**Only ALLOW permits.** DENY, ESCALATE, WAIT_FOR_AUTHORITY and DELEGATE all
block, and so does any decision a caller has never heard of. A caller that
tests for a list of blocking codes rather than for permission grants authority
the moment a new decision is added — see §6.6.

### 6.5 Inter-loop contracts

The most common failure in multi-loop architectures is not a bad loop — it is an undefined interface between loops. Each boundary carries exactly one artifact type.

| From → To | Artifact | Cadence | Integrity requirement |
|---|---|---|---|
| Execution → Learning | **Evidence Record** — signed, in the sink | Per task | GV-03; immutable at write |
| Learning → Execution | **Canonical Lesson** — kernel-promoted | Per promotion | GV-09; criteria recomputed kernel-side |
| Learning → Evolution | **Weakness Signal** — aggregated failure class, not an instance | Per window | Requires N distinct episodes |
| Evolution → Execution | **Ratified Change** — versioned, rollback-tested | Per release | GV-05, GV-07 |
| Any → Governance | **Authority Request** | Synchronous, **at grant only** | GV-01, GV-02 |
| Governance → Any | **Verdict + obligation** | Synchronous | GV-03 |
| Any → Audit stream | **Action record**, joined to its lease | Asynchronous, within envelope | GV-02, GV-06 |

A lesson the execution loop never retrieves, and a weakness signal raised from a single episode, are the two most common ways these loops appear to run while producing nothing.

### 6.6 The gate's callers — the boundary nobody watches

D-07 settled how the enforcement layer reaches the gate: **it invokes the gate
as a subprocess at each of the five events and refuses the grant on any
non-zero exit.** The alternatives — an in-process import, a long-running
service, a generated policy file the caller evaluates — were scored and
rejected; the generated-policy option most firmly, because a copy of the gate's
decisions living on the far side of a boundary goes stale silently.

This is the cheapest possible integration and it moves the **entire enforcement
burden across a process boundary.** The gate can return DENY perfectly and
license nothing, because the thing issuing the lease is elsewhere. Four ways a
caller looks correct and licenses everything:

1. It blocks on the DENY exit code and treats ESCALATE as success — three of
   the four blocking decisions become grants.
2. It treats a gate fault (bad registry, unreadable attestations) as no
   objection.
3. It treats an exit code it has never seen as permission, so adding a decision
   on the gate side silently widens authority on the caller side.
4. It drops the named verifier on the way to the gate. Nothing fails, and
   NX-INV-2 is switched off entirely.

None of these produces an error, and each passes the test its author would
write. **So D-07 is the shell-out *plus* a caller conformance suite, not the
shell-out alone.** A caller is driven through a scripted gate returning each
decision and each fault, and must refuse on all of them and issue on ALLOW;
two further checks confirm it called the gate at all, and that the request
reaching the gate is the request it was handed.

> **Reversal trigger:** a grant path found in production that did not call the
> gate; a verdict cached or reused across grants; or the conformance suite
> absent from the caller's CI for two consecutive releases.

---

## 7. Effective intelligence — the preconditions

**This section changed shape** (ILR-001-DR D-04, amending v0.1). What follows
is normative; the formula that used to lead it is now §7.2 and is not.

### 7.1 The precondition set

A band is licensed only when **all** of these hold. Each is a boolean with a
stated evidence requirement, and a single `false` blocks the band.

| # | Precondition | Holds when | Evidence |
|---|---|---|---|
| **P1** Capability | The band's dependency closure is attained | Every band it depends on is attained | Band attestations |
| **P2** Reasoning | Unaided correctness is at or above the band's floor | First-pass rate on the sealed exam ≥ floor | T2 sealed exam |
| **P3** Learning | Promoted knowledge is retrievable and traced | Every canonical lesson binds to the evidence justifying it | GV-09 |
| **P4** Action | Execution stays inside granted authority | No action without a prior lease covering its scope | GV-02 |
| **P5** Verification | **The judge is not the performer** | Performer ≠ verifier, and the verifier holds no write authority over what it verifies | GV-04, NX-INV-2 |
| **P6** Governance | Every control the band requires currently holds | All `●` in the band's §5.3 row attested and fresh | GV-01…GV-10 |

**P5 is the one that ends projects.** It is not a score to optimise, it is a
gate that shuts. A verifier that can change the thing it is verifying is a
second party with a stake, not an independent one — so both the identity test
and the authority test are enforced, and both fail closed on any ambiguity in
the name being compared.

### 7.2 The product form — retained, non-normative

$$I_{effective} = C \times R \times L \times A \times V \times G$$

Kept in the rationale because it states the principle memorably: the terms
multiply, so **any zero zeroes the product**. That is the precise mathematical
statement of *more intelligence ≠ more freedom*.

**It is not the operational form, and it must not be reported.** Its entire
operational content is *any zero blocks the band* — which is a conjunction,
and §7.1 is that conjunction written out. Everything else the formula appears
to say (that 0.8 beats 0.6, that terms trade off against each other) is either
false or unusable, because multiplying ordinal scores is not statistically
meaningful.

Three reasons the boolean form replaced it rather than sitting beside it:

- **A conjunction of named booleans compiles to config.** A `[0,1]` product
  does not: someone has to pick a threshold, and the threshold argument never
  ends.
- **An auditor reading a multiplied ordinal index** sees either a category
  error or an attempt to make a judgement look quantitative. A precondition
  checklist with an evidence requirement per line is the form assurance work is
  expected to take.
- **A number invites comparison, and comparison invites the board slide.** A
  caveat in §7 does not survive the first executive summary someone else writes
  from this document. v0.1 carried exactly that caveat, and this is the
  amendment that admits a caveat is not a control.

> **Reversal trigger:** a client or regulator requires a quantified maturity
> index. Build a purpose-built one for that requirement — never the product
> form, and never as the framework's own metric.

---

## 8. Machine-readable registry — shipped

The gate matrix is config the enforcement layer reads, not prose in a document.
**It exists**: `src/neuraxis/config/neuraxis.yaml` in `bstBizEra/neuraxis`,
loaded by a registry that refuses to load at all rather than load partially.

v0.1 printed a copy of the YAML here. That copy is removed, because a copy of a
config inside a document is the same failure this framework warns callers
about: it goes stale silently, and a reader trusts it. **What remains is the
matrix in §5.3, and a test asserts that the §5.3 table and the shipped registry
agree.** If someone changes a band's control set in one place and not the
other, CI fails.

What the registry carries per entry, beyond what v0.1 sketched:

| Field | Purpose |
|---|---|
| `band` | The only unit that is attested (D-02) |
| `question` | The capability's core question, unchanged from the model |
| `envelope_bounded` | IL-13a only; must agree with `authority.envelope_required` or the registry does not load |
| `max_age` per control | Per-control freshness. A global window forces a rollback drill onto a daily cadence, which guarantees it gets stubbed — and a stubbed drill is a vacuous probe |
| `kind` per control | `probe` or `audit`. Decides which conformance scenarios a source must answer. **Declared by the kernel, not by the source**, so a source cannot declare its way out of the vacuity check |
| `authority.role_grants` | Which roles may exercise which bands |
| `authority.non_delegable` | IL-31, IL-32, IL-33 — always require a human ratification reference, whatever the band state |
| `authority.envelope_signers` | Who may declare an envelope. **Ships empty on purpose**: no principal registry exists until T1, so naming one would be a list of strings pretending to be an allowlist. `validate` reports it as a warning rather than passing it in silence |

The eight-field per-capability pattern v0.1 promised — *state → trigger →
decision → authority → action → evidence → learning → promotion/rollback* — is
**not** stored per IL entry. It is the shape of the system, not of a registry
row: `state` and `trigger` belong to the loops (§6), `decision` and `authority`
to the gate, `evidence` to the sink, `learning` to the inter-loop contracts
(§6.5), and `promotion/rollback` to the Evolution Loop. Duplicating it per
capability would create thirty-four copies of one contract to keep in sync.

```bash
neuraxis validate      # the registry loads with its invariants intact, or not at all
neuraxis status        # band attainment against current attestations
neuraxis drift         # is the registry on disk the ratified one?
neuraxis roadmap       # what is actionable now, resolved against the live gate
```

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

**Stop reading tables like this one and ask the tool.** A current-state table in
a document is a snapshot that ages; `neuraxis status` resolves band attainment
from the registry and the attestation store at the moment it is asked.

### 10.1 What is attested today: nothing

**Zero bands are attained.** Not "Band A and B attained" — zero. The correct
reading is not that the system got worse; it is that v0.1's table recorded
*judgement*, and D-02 requires band state be recorded as *attestation*. Four of
ten controls have a wired provider and none is currently attested, so every
band is closed.

This is the framework working. An unattested control is not a control, and a
band resting on one is not attained. A fresh checkout attains nothing, and
anyone surprised by that has the wrong model of what the gate is for.

| Band | Judgement (v0.1, informal) | Attested (normative) | Root blocker |
|---|---|---|---|
| BAND-A | Attained | **Not attained** | GV-01, GV-03 unattested |
| BAND-B | Attained in practice | **Not attained** | BAND-A |
| BAND-C | In progress | **Not attained** | T1 → GV-01/02/03 |
| BAND-D | Partial | **Not attained** | BAND-B |
| BAND-E | Not started | **Not attained** | BAND-B |
| BAND-F | Under construction | **Not attained** | T1 |
| BAND-G | Not attainable | **Not attained** | BAND-F |

The judgement column is retained for one reason: it is what a reader believes
until the attestation column exists, and the gap between the two is the honest
description of where a governance programme actually is.

### 10.2 The freeze

**No new authority grants — to any agent, in any band — are permitted** until
the verifier-independence deny rule and the gate matrix are live *at lease
issuance*. Specifically: no new tool leases or scope widenings, no band
transitions, no self-modification of any kind (including changes a team would
classify as "configuration"), and no verifier assignment where performer and
verifier share a principal or an envelope.

**Capability work inside an already-attested envelope continues normally.** The
freeze is on authority, not on delivery — which is the whole point of D-03's
grant-time/within-envelope split.

> **It lifts when each of the five blocking events in §6.4 has an enforcement-
> layer entry point, and each of those entry points passes the caller
> conformance suite.** Five conforming entry points — not four, and not one
> entry point tested five times.

### 10.3 The limit that has not moved

Everything above sits on an **unauthenticated substrate**. Identities, issuers,
signers and accountable parties are self-declared strings; the waiver and
envelope files are ordinary append-only files that the audited party can also
write; and omission stays undetectable, because every check audits records that
are present with no way to know which are absent.

So the honest reading of "the invariants are enforced" is: **enforced against an
honest mistake, a careless script, and a rule quietly eroded under schedule
pressure** — which is what they were written for. Not against a determined
author of the file.

The instinct to build KBS-001 before opening self-modification is Band F before
Band G. That sequencing was already correct; this document supplies the reason
and the gate that holds it when schedule pressure arrives.

---

## 11. Decisions — status

v0.1 listed six open decisions for the operator. All six are ruled, and the
register added five more. This table is the index; ILR-001-DR carries the
scoring and the reversal triggers.

| ID | Decision | Ruling |
|---|---|---|
| **N-01** | Adopt "BST Neuraxis" as framework name | **Ruled: yes.** Three names, three jobs — *BST Neuraxis* the framework, *Governed Evolution* the principle for client-facing use, *ILR-001* the artifact |
| **N-02** | Relocate IL-13 to BAND-G | **Ruled: no — split it.** D-01. IL-13a Band C (envelope-bounded), IL-13b Band G |
| **N-03** | Governance as synchronous gate, not fourth loop | **Ruled: yes, at authority-grant.** D-03. Not on every decision |
| **N-04** | Band attestation max age | **Ruled: 24h default, per-control override.** A single global window is wrong in both directions |
| **N-05** | Whether IL-32 is ever separately enabled | **Ruled: never.** Component of IL-33 only |
| **N-06** | Publish Neuraxis externally as BST IP | **Partially settled.** The artifact repository is public; the framework document is not issued externally until §13's open items close |
| **D-02** | Banded graph vs ladder | Banded DAG canonical; ordinal claims prohibited externally |
| **D-04** | The formula | Retired to non-normative; §7 is a boolean precondition set |
| **D-05** | Capability–Authority Gate | Monotonic cumulative staircase + expiring waivers |
| **D-06** | KBS-001/T1 as the Band C blocker | Derived from the matrix; GV-01/02/03/08 non-compensable |
| **D-07** | How the enforcement layer reaches the gate | Subprocess invocation + a caller conformance suite |

### Still open, and owned by the operator

| # | Open item | Why it is not Claude's to close |
|---|---|---|
| **O-1** | **T1 — the kernel boundary.** Blocks every band above B | Requires repository-visibility and identity-issuance decisions that mint credentials on the owner's account |
| **O-2** | **T3 / T4 — lesson schema and promotion thresholds** | Blocks the Canonical Lesson contract, then GV-09 |
| **O-3** | **E-13 — the kill-switch drill procedure** | Blocks GV-10. A provider auditing a drill nobody runs is the vacuous probe |
| **O-4** | **A host for the recurring assurance run** | Without it every band closes a day after its last attestation |
| **O-5** | **A nominated BST-SA workstream to gate end to end** | The v1.0 claim is a workstream actually running under the gate |
| **O-6** | **The five enforcement-layer entry points** | Owned by L0. This is what lifts the freeze |

---

## 12. Summary

The target is not autonomous AI. It is:

> **Evidence-driven, self-improving, self-governing agentic intelligence operating within explicit human-defined authority.**

BST Neuraxis makes that statement enforceable by pairing every capability band
with the governance controls that license it, and by making the pairing config
the enforcement layer reads rather than documentation. The 33 capabilities are
unchanged. What is added is the axis they hang on, the gate they must pass, and
the correction that assurance precedes evolution rather than following it.

What v0.2 adds to that sentence is smaller and harder: **every correction in
this document now has a place where it fails.** The pairing rule is a registry
that refuses to load. The verifier-independence rule is a denial with a reason
string. The non-compensable floor is a constant in code that a config cannot
widen. The prohibition on ordinal claims is a communications control with a
named reversal trigger. And the boundary where the whole thing could be quietly
bypassed — a caller that reads the gate's answer wrongly — has a suite that
fails when it does.

A framework whose rules have no enforcement point is a framework that loses to
schedule pressure. That is the claim this document makes about agentic systems,
and v0.2 is the version that stops exempting itself from it.

---

## 13. Revision history

| Version | Change |
|---|---|
| 0.1 | Initial. Named framework; converted IL ladder to banded dependency graph; added GV axis and Capability–Authority Gate; relocated IL-13 to BAND-G; recast Governance Loop as synchronous gate; defined inter-loop contracts; made the effective-intelligence formula operational with the V=0 veto; mapped to KBS-001 and the T1–T5 queue |
| **0.2** | Amended against ILR-001-DR Rev A and its D-07 addendum. **§2.4** records what the register changed and why. **§4** — IL-13 split rather than relocated (D-01), and the prohibition on ordinal attainment claims added (D-02). **§5.4/5.5** — monotonicity as NX-INV-5, the waiver contract, and the non-compensable floor as NX-INV-4 (D-05, D-06). **§6.1/6.4/6.5** — the gate removed from the per-task execution path and scoped to five authority-changing events, with the async revoke-only observer named (D-03). **§6.6** — the caller boundary and its conformance requirement (D-07). **§7** — the formula retired to non-normative; §7.1 is now a boolean precondition set (D-04). **§8** — the inline YAML copy removed in favour of the shipped registry, with §5.3's matrix pinned to it by a test. **§10** — current state restated as attestation rather than judgement, which changes every row; the freeze and the unauthenticated-substrate limit recorded. **§11** — all six v0.1 open decisions ruled, five register rulings added, and six items that remain open listed with why each is the operator's |

### What v0.2 does not resolve

Three things, named rather than implied:

1. **The substrate.** §10.3. Until T1, every principal string is self-declared.
2. **The third clause of NX-INV-2.** *A verifier that is controlled by the
   performer* needs a principal graph that does not exist until T1 issues real
   identities. A check that always answers "no control relation known" is the
   vacuous probe this framework refuses everywhere else, so it is deliberately
   absent rather than stubbed.
3. **Omission.** Every check here audits what is present. A capability nobody
   registered, a control nobody wired, an authority path nobody declared: none
   is detected. That is the failure mode this framework does not close, and the
   honest thing is to say so in the document rather than discover it in an
   audit.
