#!/usr/bin/env python3
"""A reference gate caller that conforms (ILR-001-DR D-07).

Copy this. It is the shortest honest implementation of the caller half of
`docs/L0-LEASE-GATE-CONTRACT.md`, and like the reference attestation source it
is deliberately boring: read the lease request on stdin, ask the gate, issue
the lease only on exit 0.

The whole file is forty lines of logic and roughly half of it is refusal. That
ratio is the point. Every line below that looks like defensive noise is a
failure this suite has a scenario for:

  * `_gate_argv` resolves the binary from NEURAXIS_BIN / NEURAXIS_BIN_ARGS
    rather than hard-coding it, so the suite can substitute a scripted gate. A
    caller that hard-codes the path cannot be tested, and an untested caller
    is an unproven one.
  * The exit-code test is `!= 0`, never `== 10`. ESCALATE is exit 11, and a
    caller that blocks only on DENY grants authority on an escalation.
  * A verdict that does not parse, does not name ALLOW, or disagrees with the
    exit code refuses. An exit 0 with nothing on stdout is not an ALLOW: there
    is no verdict id to record against the lease, so nothing could later show
    the lease was licensed.
  * `timeout=` is set and its expiry refuses. A gate that did not answer has
    not consented.
  * The request is forwarded unchanged. Dropping `verifier` on the way through
    would not fail anything here and would switch off W9 entirely.

Replace `_issue_lease` with the real L0 grant. Keep everything above it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

GATE_TIMEOUT_SECONDS = 15.0
PERMITTING_DECISION = "ALLOW"
PERMITTING_EXIT = 0


def _gate_argv() -> list[str]:
    """Where the gate lives. Substitutable, on purpose."""
    binary = os.environ.get("NEURAXIS_BIN", "neuraxis")
    raw = os.environ.get("NEURAXIS_BIN_ARGS", "")
    leading: list[str] = []
    if raw.strip():
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("NEURAXIS_BIN_ARGS must be a JSON array")
        leading = [str(part) for part in parsed]
    return [binary, *leading, "--json", "gate", "-"]


def _ask_gate(request: dict) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            _gate_argv(),
            input=json.dumps(request, sort_keys=True),
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        # A gate that did not answer has not consented.
        return -1, "", f"gate did not answer within {GATE_TIMEOUT_SECONDS:g}s"
    except OSError as exc:
        # No gate reachable is not a gate that said yes.
        return -1, "", f"could not run the gate: {exc}"
    return completed.returncode, completed.stdout, completed.stderr


def _refuse(reason: str) -> int:
    print(f"lease refused: {reason}", file=sys.stderr)
    return 1


def _issue_lease(request: dict, verdict: dict) -> int:
    """The real grant goes here. It runs only on a verified ALLOW."""
    print(
        json.dumps(
            {
                "record": "lease",
                "principal": request["identity"],
                "issued_by": "l0-gate",
                "scope": [request["scope"]],
                "verdict_id": verdict.get("verdict_id"),
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as exc:
        return _refuse(f"lease request is not JSON: {exc}")
    if not isinstance(request, dict):
        return _refuse("lease request is not a JSON object")

    code, stdout, stderr = _ask_gate(request)

    # Test for zero. Not for 10, and not for a list of codes this file happens
    # to know: an exit code nobody recognised must not read as unblocked.
    if code != PERMITTING_EXIT:
        return _refuse(f"gate exit {code}: {(stderr or stdout).strip() or 'no detail'}")

    try:
        verdict = json.loads(stdout)
    except ValueError:
        return _refuse("gate exited 0 but returned no verdict; nothing licensed this lease")
    if not isinstance(verdict, dict):
        return _refuse("gate returned something that is not a verdict")
    if verdict.get("decision") != PERMITTING_DECISION:
        # Exit code and verdict disagree. One of them is wrong and there is no
        # way to tell which, so no verdict from this run is trustworthy.
        return _refuse(
            f"exit {code} means {PERMITTING_DECISION} but the verdict says "
            f"{verdict.get('decision')!r}; refusing the whole run"
        )

    return _issue_lease(request, verdict)


if __name__ == "__main__":
    sys.exit(main())
