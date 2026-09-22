#!/usr/bin/env bash
# SessionStart: put the project's real state in front of the agent before it
# starts reasoning about the project's state.
#
# Harness section 3: "Do not infer current project state from chat summaries
# when the repository contains authoritative state." The repository contains
# it, and it is executable -- `neuraxis status` reads the attestation ledger
# and `neuraxis roadmap` resolves every gate against the live gate. Both are E5
# under the evidence classes: a current run, not a document about one.
#
# The asymmetry with kernel_guard.py is deliberate. The guard is a control, so
# it fails closed. This is orientation, so it fails quiet: if `neuraxis` is not
# installed yet the session should still start, and an agent that sees no state
# block goes and runs the commands itself. A SessionStart hook that aborted the
# session because a dev environment was half-built would be removed within a
# day, and then the guard would go with it.

set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

state=""
add() { state+="$1"$'\n'; }

add "## Live project state (SessionStart, $(date -u +%Y-%m-%dT%H:%MZ))"
add ""
add "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown) @ $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
add "Working tree: ${dirty} changed path(s)"
add ""

if command -v neuraxis >/dev/null 2>&1; then
    add '### Band attainment (`neuraxis status`)'
    add '```'
    add "$(neuraxis status 2>&1 | head -20)"
    add '```'
    add ""
    add '### Actionable now (`neuraxis roadmap --next`)'
    add '```'
    add "$(neuraxis roadmap --next 2>&1 | head -20)"
    add '```'
    add ""
    add "This is E5 evidence and it supersedes any recollection of project state."
    add "For blockers and their review dates: \`neuraxis roadmap\`."
else
    add "\`neuraxis\` is not on PATH, so no band or roadmap state was read."
    add "Run \`pip install -e \".[dev]\"\`, then \`neuraxis status\` and \`neuraxis roadmap\`"
    add "before asserting anything about what is blocked or attained."
fi

python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":sys.stdin.read()}}))' <<<"$state"
