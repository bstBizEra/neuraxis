---
name: next-action
description: Choose what to do next — generate competing directions, score them, apply the project-path rule, and check authority before executing. Use when work finishes, when a session resumes with no instruction, or when the obvious next step should be challenged.
---

# Choosing the next action

Two distinct questions, and conflating them is how an agent ends up doing the
strategically interesting thing while the gate it actually depends on stays
red.

```
which direction is best?          →  scoring
which action may run next?        →  the project path
```

## 1. Generate competing directions

At least three, materially different. "Do the obvious thing" and "do the
obvious thing carefully" is one direction. Include, deliberately:

- the direction that **unblocks something else**, even if it is small
- the direction that **converts a prose control into a mechanism**
- the direction that **does nothing locally and names a human decision**

The last one is a real option in this repository and it wins more often than
it feels like it should. Most items are blocked on externals owned by
OP-Vily; an hour of local work that cannot move a gate scores worse than a
dated decision recorded against the blocker.

## 2. Score

Weigh by: does it unblock a gate, does it reduce the chance of a silent
failure, is it reversible, is it within authority, what does it cost, what
does it foreclose. Assign one of:

```
RECOMMENDED   VIABLE   RESEARCH_REQUIRED   BLOCKED   NOT_READY   REJECTED
```

Exactly one primary recommendation unless the evidence is genuinely tied.

Report confidence as `HIGH` / `MEDIUM` / `LOW`, and mean it:

- `HIGH` — direct evidence, key assumptions resolved
- `MEDIUM` — supported, material assumptions remain
- `LOW` — insufficient or conflicting evidence

**`LOW` means the next action is research, not speculative implementation.**

## 3. The project path wins

The highest-scoring direction is not automatically executable:

```
best direction → dependencies → current gate → authority → next executable action
```

Worked example from this repository: implementing GV-09's provenance binding
scores well on architecture. But `PKG-GV-09` waits on `PKG-LOOP-CONTRACTS`,
which waits on externals T3 and T4, which are owned and undated by me.
Therefore the next action is not GV-09; it is whatever moves T3/T4 towards a
decision, or work that is genuinely ungated.

That example is also how `PKG-GV-05` got unblocked: it had been bundled with
GV-09 behind T3/T4 that it did not actually need. **Check whether a blocker is
a real dependency or a packaging artefact before accepting it.** That check is
cheap and it has paid twice.

## 4. Check authority before executing

```
Is it required by the current objective?      no  → do not execute
Is it inside the existing envelope?           no  → WAIT_FOR_AUTHORITY
Is it reversible and bounded?                 no  → propose and wait
Does it cross a governance boundary?          yes → propose and wait
```

Self-authorisation means acting within authority that already exists. It never
means creating authority. In this repository the boundaries that are not mine
are listed in `CLAUDE.md` — kernel, evidence, waivers, seats, releases — and
the first two are enforced by `.claude/hooks/kernel_guard.py` rather than by my
agreement with them.

## 5. Report

State the recommendation, the runners-up and why they lost, the confidence and
what would raise it, and the single next executable action. If that action is
"a human decides", name the decision, the owner, and the date it gets looked
at — an undated blocker is an indefinite one, which is how a wait becomes a
stall.
