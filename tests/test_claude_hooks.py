"""The .claude/ guard is held to the same four rules as a provider.

A `PreToolUse` hook fires inside the Claude Code harness, where nothing in this
package can observe it -- which makes it precisely the kind of control that
rots unnoticed. So it is exercised here the way `src/neuraxis/providers/` are
exercised: fail closed, positive control, vacuity probe, and the refusal has to
cite its evidence.

The vacuity probe is the one that matters. A guard that denied every write
would pass any test asking "does it refuse the kernel?" while being useless,
because the first thing anybody would do is switch it off. So `test_ordinary_*`
is not a courtesy check; it is the control that keeps the refusals meaningful.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / ".claude" / "hooks" / "kernel_guard.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
KERNEL = "src/neuraxis/config/neuraxis.yaml"


def run_guard(payload: object) -> tuple[int, dict | None]:
    """Invoke the hook exactly as the harness does: JSON on stdin."""
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload) if not isinstance(payload, str) else payload,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def decision_of(result: dict | None) -> str:
    if result is None:
        return "allow"
    return result["hookSpecificOutput"]["permissionDecision"]


def reason_of(result: dict) -> str:
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def write(path: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path}}


def bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# --- the control itself -----------------------------------------------------


def test_the_kernel_cannot_be_written():
    """The line in neuraxis.yaml that says agents hold no write path to it."""
    code, result = run_guard(write(KERNEL))
    assert code == 0
    assert decision_of(result) == "deny"
    assert "KERNEL" in reason_of(result)


def test_the_kernel_cannot_be_written_by_absolute_path():
    """Relative and absolute name the same file; only one being refused is a bypass."""
    code, result = run_guard(write(str(REPO_ROOT / KERNEL)))
    assert code == 0
    assert decision_of(result) == "deny"


def test_the_kernel_cannot_be_reached_through_a_parent_traversal():
    code, result = run_guard(write(f"tests/../{KERNEL}"))
    assert decision_of(result) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        f"echo 'GV-01: {{}}' > {KERNEL}",
        f"sed -i s/BAND-A/BAND-G/ {KERNEL}",
        f"rm {KERNEL}",
        f"cat /tmp/x | tee {KERNEL}",
    ],
)
def test_shell_mutation_of_the_kernel_is_refused(command):
    code, result = run_guard(bash(command))
    assert decision_of(result) == "deny", command


def test_reading_the_kernel_from_the_shell_is_fine():
    """The guard governs writes. A registry nobody may read is not the rule."""
    assert decision_of(run_guard(bash(f"cat {KERNEL}"))[1]) == "allow"
    assert decision_of(run_guard(bash("neuraxis validate"))[1]) == "allow"


# --- evidence ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "attestations.jsonl",
        "drill-log.jsonl",
        "task-log.jsonl",
        "gate-log.jsonl",
        "lease-log.jsonl",
        "waivers.jsonl",
    ],
)
def test_evidence_cannot_be_authored(path):
    """The shortest route to an undeserved band is a typed line in a log."""
    code, result = run_guard(write(path))
    assert decision_of(result) == "deny", path
    assert "evidence" in reason_of(result).lower()


def test_the_refusal_names_the_control_the_file_feeds():
    """A denial that does not say what it protects gets read as an obstacle."""
    _, result = run_guard(write("drill-log.jsonl"))
    assert "GV-05" in reason_of(result)


def test_appending_to_a_log_from_the_shell_is_refused():
    code, result = run_guard(bash('echo \'{"drill_id":"x"}\' >> drill-log.jsonl'))
    assert decision_of(result) == "deny"


def test_the_sanctioned_producer_still_runs():
    """The drill runner writes the drill log. That is the whole point of it.

    If this ever flips to deny, the guard has stopped distinguishing evidence
    that was witnessed from evidence that was typed, and the honest move is to
    delete the guard rather than route around it.
    """
    command = "python scripts/rollback_drill.py --log drill-log.jsonl --performer agent"
    assert decision_of(run_guard(bash(command))[1]) == "allow"


def test_a_heredoc_body_that_merely_discusses_a_protected_file_is_not_a_write():
    """The commit message for this guard was itself refused by an earlier draft.

    Writing about the kernel and the evidence logs by name is the normal case
    in this repository -- commit messages, docs, test fixtures. A guard that
    turned every one of those into a refusal would be switched off inside a
    week, and the real rule would go with it.
    """
    command = (
        "git commit -F - <<'EOF'\n"
        "guard: refuse writes to src/neuraxis/config/neuraxis.yaml\n"
        "and to drill-log.jsonl, because evidence is emitted, never typed.\n"
        "EOF\n"
        "git log --oneline -1"
    )
    assert decision_of(run_guard(bash(command))[1]) == "allow"


def test_a_heredoc_that_targets_a_protected_file_is_still_refused():
    """Stripping the body must not strip the redirection that names the target."""
    command = "cat >> drill-log.jsonl <<'EOF'\n{\"drill_id\": \"x\"}\nEOF"
    assert decision_of(run_guard(bash(command))[1]) == "deny"


def test_evidence_outside_the_repository_is_not_this_guards_business():
    """Tests build logs in tmp_path; refusing that would push them to weaker fixtures."""
    assert decision_of(run_guard(write("/tmp/pytest-of-x/drill-log.jsonl"))[1]) == "allow"


# --- the guard's own files --------------------------------------------------


@pytest.mark.parametrize(
    "path", [".claude/settings.json", ".claude/hooks/kernel_guard.py"]
)
def test_changing_the_guard_asks_rather_than_denies_or_allows(path):
    """Neither self-editing nor unmaintainable. The decision goes to a human."""
    code, result = run_guard(write(path))
    assert decision_of(result) == "ask", path


# --- positive control: the probe that keeps the refusals meaningful ---------


@pytest.mark.parametrize(
    "path",
    [
        "src/neuraxis/gate.py",
        "src/neuraxis/config/roadmap.yaml",
        "docs/ROADMAP.md",
        "tests/test_gate.py",
        "README.md",
    ],
)
def test_ordinary_files_are_untouched(path):
    """Vacuity probe. A guard that refuses everything is a guard nobody keeps."""
    code, result = run_guard(write(path))
    assert code == 0
    assert decision_of(result) == "allow", path


def test_roadmap_yaml_is_writable_but_the_kernel_is_not():
    """Both are config/*.yaml. Only one decides what licenses a band.

    This pair is the guard's discrimination in one assertion: if it ever
    protects by directory rather than by what the file governs, this fails.
    """
    assert decision_of(run_guard(write("src/neuraxis/config/roadmap.yaml"))[1]) == "allow"
    assert decision_of(run_guard(write(KERNEL))[1]) == "deny"


# --- fail closed ------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        '{"tool_name": "Write", "tool_input": "a string, not an object"}',
        '{"tool_name": "Write", "tool_input": {}}',
        '{"tool_name": "Bash", "tool_input": {"command": null}}',
        "[1, 2, 3]",
    ],
)
def test_an_undecidable_payload_denies(payload):
    """Same doctrine as the gate: absence and malformation are DENY, not skip."""
    code, result = run_guard(payload)
    assert code == 0, "a hook that exits non-zero is reported as broken, not as a refusal"
    assert decision_of(result) == "deny", payload


def test_an_empty_payload_is_not_a_write_and_is_allowed():
    """Distinct from the case above: no tool named is not a malformed write."""
    assert decision_of(run_guard("{}")[1]) == "allow"


# --- the wiring -------------------------------------------------------------


def settings_json() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8-sig"))


def test_settings_json_is_valid_and_installs_the_guard():
    """A malformed settings.json silently disables every setting in the file.

    Which would disable the guard, leaving a repository that believes it has
    one. That failure is invisible from inside a session, so it is asserted
    here where CI can see it.
    """
    settings = settings_json()
    matchers = [
        entry
        for entry in settings["hooks"]["PreToolUse"]
        if "kernel_guard" in json.dumps(entry)
    ]
    assert matchers, "settings.json does not install kernel_guard.py"
    for entry in matchers:
        for tool in ("Write", "Edit", "Bash"):
            assert tool in entry["matcher"], f"{tool} is not matched"


def test_every_hook_settings_points_at_a_file_that_exists():
    """A hook whose script is missing reports nothing and blocks nothing."""
    referenced = 0
    for event in settings_json()["hooks"].values():
        for entry in event:
            for hook in entry["hooks"]:
                for match in re.findall(r"\.claude/[\w./-]+", hook["command"]):
                    referenced += 1
                    assert (REPO_ROOT / match).is_file(), match
    assert referenced >= 2, "expected the guard and the session-state script"
