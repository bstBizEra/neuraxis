#!/usr/bin/env python3
"""PreToolUse guard: the two files an agent in this repository may not author.

`src/neuraxis/config/neuraxis.yaml` carries this line on its second row:

    # This file is KERNEL under KBS-001 (K-04 family). Agents hold no write path to it.

Until this hook existed that sentence was a comment. An agent that read it
carefully complied; an agent that did not, or that never read line 2, wrote to
the kernel and nothing objected. A control enforced by the care of the party it
constrains is the exact failure this repository exists to prevent -- and the
kernel is the file that says which controls license which bands, so an agent
with a write path to it can grant itself anything.

The second class is evidence. `.gitignore` says it plainly: "Runtime state -
never source." A `.jsonl` in the working root is an operational record --
attestations, task log, gate log, lease log, drill log. `neuraxis assure` reads
those files and attests controls from them, and the gate opens bands from the
attestations. So an agent that can type a line into `drill-log.jsonl` can open
BAND-B without a drill ever happening. Evidence is emitted by a tool that
witnessed the event; it is never typed by the party it exonerates (ADR-0010).

Three decisions, and the third is the interesting one:

    deny   the kernel registry, and evidence files in the working root
    ask    this hook and the settings that install it
    allow  everything else

`ask` rather than `deny` for the guard's own files because a guard nobody can
change is not a stronger control, it is an unmaintainable one -- but a guard
that edits itself without anyone looking is no control at all. So the decision
goes to the human, which is what `ask` is for.

WHAT THIS DOES NOT DO, stated plainly because a guard whose limits are
undocumented gets trusted past them:

  * Write/Edit is closed. Those tools name their target, so the check is exact.
  * Bash is a speed bump, not a wall. It denies the obvious shapes -- `>`,
    `>>`, `tee`, `sed -i`, `rm`, `mv` against a protected path -- and nothing
    stops `python -c` from opening the same file. Closing that would require
    refusing to reason about shell at all. Heredoc bodies are excluded: the
    first draft of this guard refused its own commit message for naming the
    kernel, and a guard that noisy gets switched off before it ever catches
    anything.
  * It governs FILES, not CLAIMS. `neuraxis attest --control GV-05 --result
    pass` writes no protected path and this hook will not see it. The control
    on that side is the provider harness: `assure` establishes results from
    evidence rather than accepting them, and NX-INV-2 keeps the performer out
    of the verifier seat.
  * It is prompt-time only. The post-hoc detector for the kernel already exists
    and is stronger: `neuraxis drift` against the ratified digest, weekly, in
    .github/workflows/drift.yml. This hook makes the mutation fail before the
    commit rather than a week after it.

On an unexpected payload this guard DENIES. Deny-on-error is the doctrine
everywhere else in this package (see src/neuraxis/gate.py: absence, expiry,
malformation and an internal exception all produce DENY), and a guard that
failed open on a payload it did not recognise would be a vacuous check wearing
a hook's hat. There is deliberately no environment variable to switch it off:
a bound that can be lifted from inside the thing it bounds is not a bound
(ADR-0006). To disable it, edit .claude/settings.json -- which is `ask`, so a
human sees it happen.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The kernel registry. Relative to the repository root.
KERNEL = "src/neuraxis/config/neuraxis.yaml"

#: Files that install or implement this guard. Changing them is legitimate
#: work; doing it unobserved is not.
SELF = ("\\.claude/settings\\.json$", "\\.claude/hooks/")

#: Evidence families, by basename, wherever they appear inside the repository.
#: The root-level `*.jsonl` rule below is the general case; these are named so
#: the refusal can say which control the file feeds.
EVIDENCE_FAMILIES = {
    "attestations.jsonl": "the attestation ledger the gate reads",
    "task-log.jsonl": "GV-04 verifier independence",
    "gate-log.jsonl": "GV-07 ratification",
    "lease-log.jsonl": "GV-02 authority and GV-06 containment",
    "drill-log.jsonl": "GV-05 reversibility",
    "evidence-sink.jsonl": "the evidence sink",
    "waivers.jsonl": "the recorded exception path",
    "envelopes.jsonl": "declared capability bounds",
}

#: Shell shapes that write. Matched against the whole command, so a hit only
#: means "this command writes somewhere"; it is paired with a protected-path
#: mention before anything is refused.
SHELL_WRITES = re.compile(
    r"(>>?\s|\|\s*tee\b|\bsed\b[^|;]*\s-i|\brm\b|\bmv\b|\bcp\b|\btruncate\b|\bdd\b"
    r"|\bchmod\b|\bchown\b|\bln\b|\bgit\s+checkout\b|\bgit\s+restore\b)"
)

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

#: `cmd <<'EOF' ... EOF`. The body is data handed to a program, not shell, and
#: in this repository the normal case is a commit message that discusses the
#: kernel and the evidence logs by name. Scanning it made every such commit a
#: refusal -- gratuitous noise, and noise is how a guard gets switched off. The
#: redirection target stays in the command portion, so stripping the body loses
#: nothing: `cat >> drill-log.jsonl <<EOF` is still refused.
HEREDOC = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^[ \t]*\2[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


def strip_heredocs(command: str) -> str:
    return HEREDOC.sub("<<REDACTED-BODY", command)


def _relative(raw: str) -> str | None:
    """Repo-relative POSIX path, or None if the target is outside the repo.

    Outside the repository is not this guard's business: a test writing a
    drill log into `tmp_path` is the supported way to exercise the provider,
    and refusing it would push authors towards weaker fixtures.
    """
    try:
        resolved = Path(raw).expanduser()
        if not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        resolved = Path(resolved).resolve()
        return resolved.relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError, RuntimeError):
        return None


def classify(path: str) -> tuple[str, str] | None:
    """(decision, reason) for a repo-relative path, or None if unprotected."""
    if path == KERNEL:
        return (
            "deny",
            f"{path} is KERNEL under KBS-001 (K-04). It declares which controls "
            "license which bands, so a write path to it is a path to granting "
            "yourself any capability. Propose the change to the operator; "
            "ratification is `neuraxis drift` against a released digest, not an "
            "edit. (.claude/hooks/kernel_guard.py)",
        )

    for pattern in SELF:
        if re.search(pattern, path):
            return (
                "ask",
                f"{path} installs or implements the guard that is refusing "
                "this. Changing it is legitimate work, but a guard that quietly "
                "rewrites itself is not a control. A human should see this one.",
            )

    name = Path(path).name
    fed = EVIDENCE_FAMILIES.get(name)
    root_level = "/" not in path and name.endswith(".jsonl")
    if fed or root_level:
        feeds = fed or "a governance control"
        return (
            "deny",
            f"{path} is evidence ({feeds}). `neuraxis assure` attests controls "
            "from these files and the gate opens bands from those attestations, "
            "so a hand-written line here opens a band for an event that never "
            "happened. Evidence is emitted by the tool that witnessed it -- "
            "`neuraxis attest`, `neuraxis assure`, scripts/rollback_drill.py -- "
            "never typed. (ADR-0010; .claude/hooks/kernel_guard.py)",
        )

    return None


def decide(payload: dict) -> tuple[str, str] | None:
    tool = payload.get("tool_name") or ""
    supplied = payload.get("tool_input") or {}
    if not isinstance(supplied, dict):
        return ("deny", "tool_input was not an object; this guard does not guess.")

    if tool in WRITE_TOOLS:
        raw = supplied.get("file_path") or supplied.get("notebook_path")
        if not isinstance(raw, str) or not raw.strip():
            return ("deny", f"{tool} arrived with no file path; this guard does not guess.")
        path = _relative(raw)
        return classify(path) if path else None

    if tool == "Bash":
        command = supplied.get("command")
        if not isinstance(command, str):
            return ("deny", "Bash arrived with no command string; this guard does not guess.")
        command = strip_heredocs(command)
        if not SHELL_WRITES.search(command):
            return None
        # A mention is enough here. Shell is not parsed, so the test is
        # deliberately coarse: this command writes, and it names something
        # protected. False positives cost one rephrase; a false negative costs
        # the control. Ordered so the kernel is reported before the softer
        # `ask` on this guard's own files.
        for candidate in (KERNEL, *EVIDENCE_FAMILIES, ".claude/settings.json", ".claude/hooks/"):
            if candidate not in command:
                continue
            verdict = classify(candidate)
            if verdict:
                decision, reason = verdict
                return (
                    decision,
                    reason + f"\nThe command writes and names {candidate!r}. If it does "
                    "not in fact target that file, run it a way that does not say so.",
                )
        return None

    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook payload was not an object")
        verdict = decide(payload)
    except Exception as exc:  # noqa: BLE001 - deliberate: see module docstring
        verdict = (
            "deny",
            f"the kernel guard could not evaluate this call ({exc}). Under this "
            "package's own doctrine an undecidable request is denied, not waved "
            "through. Fix .claude/hooks/kernel_guard.py.",
        )

    if verdict is None:
        return 0

    decision, reason = verdict
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
