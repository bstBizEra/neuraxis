# `.claude/` — what is here, what is not, and why

Configuration for agents working in this repository. It is deliberately small,
and the boundary is the one stated in `CLAUDE.md`: **this directory points at
authority, it never becomes authority.** The kernel, the ADRs, the decision
register and the roadmap remain the project's sources of truth; if anything
here contradicts them, they win and this is the bug.

## What is here

| Path | What it is | Enforced by |
|---|---|---|
| `../CLAUDE.md` | Source precedence, invariants, what an agent does not do here | mostly nothing — see below |
| `hooks/kernel_guard.py` | `PreToolUse`: refuses writes to the kernel and to evidence files | itself, and `tests/test_claude_hooks.py` in CI |
| `hooks/session_state.sh` | `SessionStart`: puts live band and roadmap state in front of the agent | nothing; it is orientation |
| `settings.json` | Installs both hooks | `tests/test_claude_hooks.py` |
| `skills/` | Four procedures: discovery, evidence, next action, verification | — |
| `agents/` | Four reviewers, all read-only | — |

## The one part that is a mechanism

`hooks/kernel_guard.py` exists because `src/neuraxis/config/neuraxis.yaml`
carries this on line 2:

> This file is KERNEL under KBS-001 (K-04 family). Agents hold no write path to it.

That was a comment. An agent that read line 2 complied; an agent that did not
wrote the file that decides which controls license which bands. The guard makes
the sentence true for `Write` and `Edit`, and makes the obvious shell shapes
expensive. Its limits are documented in its own module docstring rather than
left to be discovered: Bash is a speed bump, `python -c` walks past it, and it
governs files rather than claims.

It is held to the provider contract — fail closed, positive control, vacuity
probe, cite evidence — in `tests/test_claude_hooks.py`, which also runs two
mutants of the guard past its own suite to prove the suite discriminates. A
hook that silently stops firing is invisible from inside a session, so the
check lives where CI can see it.

Everything else in this directory is prose, and prose is the weak form. The
list in `CLAUDE.md` under "What an agent does not do here" should be read as a
backlog of controls worth converting into mechanisms, not as a set of rules
that are already enforced.

## What was deliberately not built

The harness specification lists eight skills, five agents and five hooks. Four,
four and two were built. Shipping the rest as stubs would have produced a
directory that looks complete and does less than it claims — which is the
failure this repository is about.

| Not built | Why |
|---|---|
| `wp-planning` skill | Imports a Work Package model this repository does not use. Work here is roadmap items with gates and `ITEM_STATES`; a parallel vocabulary would be a second source of truth about what is authorised. |
| `implementation` skill | Would have restated `CLAUDE.md` and `verification`. A skill that exists to be listed costs context on every load. |
| `research-direction` skill | The research procedure that earns its place here is the evidence and jurisdiction part, which is in `evidence-assessment`. The rest is generic. |
| `prompt-suggestion` skill | Folded into `CLAUDE.md` § Reporting. It is one paragraph of behaviour, not a procedure. |
| `project-discovery` as a state file | Discovery runs commands rather than reading a cached state file, because a cached one goes stale and gets trusted anyway. |
| `researcher` agent | The reviewers above are valuable because they are *independent* of the author. A research subagent returns summaries — E0/E1 evidence — through a channel that hides its sources. Better to research in-session where the sources stay visible. |
| `authority-check` hook | Authority in this project is decided by `neuraxis gate` and `neuraxis assist`, which already exist and already fail closed. A hook re-deciding it would be a second implementation of the gate (ADR-0004). |
| `destructive-action-guard` hook | The destructive actions that matter here are covered: kernel and evidence by `kernel_guard.py`, releases and tags by credential scope, history rewriting by the branch rules. A generic `rm -rf` matcher would mostly generate noise, and noise is how a guard gets disabled. |
| `evidence-check` hook | Checking evidence *quality* needs judgement, so it belongs in `agents/evidence-auditor.md`. Refusing to *author* evidence is mechanical, and that is in the guard. |
| `state-checkpoint` hook | State lives in git and in the attestation ledger. A checkpoint file would be a third place to disagree with them. |
| `rules/` | Nothing needed a home there that `CLAUDE.md` or a skill did not already hold. |
| `model:` in agent frontmatter | Model identifiers are kept out of repository artefacts. The agents inherit the session's model. |

## Changing this directory

`settings.json` and `hooks/` are `ask`, not `deny` — a guard nobody can change
is unmaintainable, and a guard that rewrites itself unobserved is not a guard.
So the decision goes to a human. If you disable the hook, `tests/
test_claude_hooks.py` goes red, which is the intended second signal.
