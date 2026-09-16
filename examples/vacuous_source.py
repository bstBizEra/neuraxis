#!/usr/bin/env python3
"""A source that does NOT conform, kept so the suite has something to catch.

It looks fine. It emits a well-formed attestation with a plausible evidence
reference, every time, for everyone -- which is exactly the shape of a probe
that has quietly stopped probing. `neuraxis conform` fails it on two rules:
it never reports FAIL (rule 2), and it answers the same for a powerless
identity as for a powerful one (rule 3).

This file exists because a conformance suite nobody has seen fail is itself an
unverified check.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def main() -> int:
    request = json.load(sys.stdin)
    json.dump(
        {
            "control": request.get("control", "GV-00"),
            "result": True,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "issuer": "example/vacuous-source",
            "evidence_ref": "example://looks-like-a-reference/42",
            "provenance": "provider",
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
