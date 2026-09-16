#!/usr/bin/env python3
"""A gate caller that does NOT conform, and looks entirely reasonable.

Every line here is something a competent engineer writes on a Tuesday. It calls
the gate. It checks the result. It blocks when the gate says DENY. Its authors
would test it against a DENY, watch it refuse, and ship it.

It has three holes, and `neuraxis caller-conform` finds all three:

  1. It blocks on exit 10. ESCALATE is 11, WAIT_FOR_AUTHORITY is 12, DELEGATE
     is 13 -- so three of the four blocking decisions issue the lease. This is
     the failure the README warns about and the reason the warning exists.
  2. It treats a CLI fault (exit 2) as no objection. A gate that could not load
     its registry becomes a gate that had nothing to say.
  3. It drops `verifier` when forwarding the request. Nothing fails. The gate
     simply stops being able to enforce verifier independence, which is the
     highest-ranked item in the entire decision register.

Run it against the suite to see what a plausible caller scores:

    neuraxis caller-conform -- python examples/credulous_caller.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BLOCKING_EXIT = 10  # (1) wrong: this is DENY's code, not "blocked"


def main() -> int:
    request = json.loads(sys.stdin.read())
    forwarded = {k: v for k, v in request.items() if k != "verifier"}  # (3)

    binary = os.environ.get("NEURAXIS_BIN", "neuraxis")
    leading = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
    completed = subprocess.run(
        [binary, *leading, "--json", "gate", "-"],
        input=json.dumps(forwarded),
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode == BLOCKING_EXIT:
        print("lease refused: gate denied", file=sys.stderr)
        return 1

    # (2) anything else -- including exit 2, and including an exit code from a
    # Decision added after this file was written -- falls through to the grant.
    print(json.dumps({"record": "lease", "principal": forwarded.get("identity")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
