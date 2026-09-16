#!/usr/bin/env python3
"""A reference attestation source that conforms.

Copy this. It is the shortest honest implementation of the contract in
`docs/CONFORMANCE.md`, and it is deliberately boring: read one JSON object on
stdin, do the check, write one JSON attestation on stdout.

What makes it conform is not the shape of the file. It is that each scenario
does something real:

  live       run the check for a principal that should pass
  broken     run it with the thing it depends on unavailable -- and report
             FAIL, rather than deciding absence means nothing is wrong
  negative   run it against a condition it must reject, and report FAIL
  powerless  run it as an identity with no authority, and report FAIL

The last one is what separates a probe from a decoration. A check that answers
the same for a powerful and a powerless identity is not checking authority; it
is checking that the machine is switched on.

The "check" below is a stand-in -- it asks whether a principal appears in an
access list. Replace the body of `_has_access` with the real probe and keep the
scenario wiring.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

ISSUER = "example/conforming-source"

# The stand-in check: who is allowed through the boundary this probe tests.
_ACCESS_LIST = {"kernel-admin", "assurance-probe"}


def _has_access(identity: str, *, directory_available: bool) -> bool:
    if not directory_available:
        # Fail closed. The directory being unreachable is not evidence that
        # everyone is authorised; it is evidence of nothing, and a probe that
        # reports PASS on nothing is the failure this rule exists for.
        raise RuntimeError("the access directory is unreachable")
    return identity in _ACCESS_LIST


def main() -> int:
    request = json.load(sys.stdin)
    control = request.get("control", "GV-00")
    scenario = request.get("scenario", "live")

    identity = {
        "live": "kernel-admin",
        "broken": "kernel-admin",
        "negative": "kernel-admin",
        "powerless": "nobody-at-all",
    }.get(scenario, "kernel-admin")

    directory_available = scenario != "broken"
    # `negative` points the probe at a boundary that should reject it, so a
    # working check reports FAIL. If this still passes, the check is dead.
    access_list_applies = scenario != "negative"

    try:
        allowed = _has_access(identity, directory_available=directory_available)
        result = bool(allowed and access_list_applies)
        detail = f"identity={identity!r} scenario={scenario!r}"
    except RuntimeError as exc:
        result = False
        detail = f"{exc}; reported FAIL rather than assuming access"

    json.dump(
        {
            "control": control,
            "result": result,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "issuer": ISSUER,
            # A reference, not a verdict. "pass" here would satisfy the letter
            # of rule 4 and none of it: an auditor needs somewhere to look.
            "evidence_ref": f"example://probe-run/{scenario}?detail={detail}",
            "provenance": "provider",
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    # Exit code is advisory; the attestation is the answer. Callers convert a
    # crash to FAIL, which is why a crash conforms -- but saying FAIL is better
    # than saying nothing.
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
