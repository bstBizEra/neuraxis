#!/usr/bin/env python3
"""Run a GV-05 rollback drill against a real tracked file, and emit the record.

Mutates a resource this repository actually has, rolls it back with the repo's
own tooling, and recomputes the digest to check that what came back is what was
there before. The record it writes is the input to `nx/rollback-drill`; the
contract is docs/GV-05-drill-log-contract.md.

    python scripts/rollback_drill.py --target README.md --append drill-log.jsonl

**It does not fill in `verifier`, and there is no flag to make it.** The field
says a principal other than the performer observed the restored state. This
script is the performer. Writing a name there would be the performer attesting
its own work, which is the NX-INV-2 failure the record exists to rule out --
and the resulting record would pass the audit while being false, which is worse
than no record at all.

So the drill leaves it empty and the provider refuses the record, correctly,
until somebody who is not this script verifies it and says so:

    python scripts/rollback_drill.py --verify drill-log.jsonl --as <principal>

That command recomputes the digests from the drill's own artifacts rather than
trusting the record, and only then writes the verifier in. Whoever runs it is
making the claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_drill(target: Path, drill_id: str) -> dict:
    """Mutate, roll back, and compare. Raises if the tree is not clean first."""
    rel = target.relative_to(ROOT).as_posix()
    if git("status", "--porcelain", "--", rel):
        raise SystemExit(
            f"{rel} has uncommitted changes; a drill against a dirty tree cannot "
            f"tell a restored state from an unsaved one"
        )

    baseline = digest(target)
    mutated_at = now()

    original = target.read_bytes()
    target.write_bytes(original + b"\n<!-- GV-05 drill mutation -->\n")
    after_mutation = digest(target)
    if after_mutation == baseline:
        raise SystemExit("the mutation did not change the file; this drill would be vacuous")

    # Roll back with the repository's own tooling, not by writing `original`
    # back: restoring from a variable in this process proves this process can
    # remember bytes, which is not the property under test.
    git("checkout", "--", rel)
    rolled_back_at = now()
    restored = digest(target)

    return {
        "drill_id": drill_id,
        "mutation_class": "tracked-file",
        "performer": "neuraxis-drill-runner",
        "verifier": "",
        "outcome": "restored" if restored == baseline else "failed",
        "mutated": [rel],
        "restored": [rel] if restored == baseline else [],
        "baseline_digest": baseline,
        "restored_digest": restored,
        "mutated_digest": after_mutation,
        "mutated_at": mutated_at,
        "rolled_back_at": rolled_back_at,
        "verified_at": "",
        "commit": git("rev-parse", "HEAD"),
        "evidence_ref": f"git://{git('rev-parse', 'HEAD')}#{rel}",
    }


def verify(record: dict, principal: str) -> dict:
    """Recompute from the artifacts rather than trusting the record."""
    if not principal.strip():
        raise SystemExit("--as must name the principal making the claim")
    if principal.strip() == record.get("performer"):
        raise SystemExit(
            f"{principal} performed this drill; a performer verifying its own work "
            f"is exactly what the record exists to rule out (NX-INV-2)"
        )
    for rel in record["mutated"]:
        observed = digest(ROOT / rel)
        if observed != record["baseline_digest"]:
            raise SystemExit(
                f"{rel} is not at the recorded baseline now ({observed} != "
                f"{record['baseline_digest']}); this drill cannot be verified after the fact"
            )
    record["verifier"] = principal.strip()
    record["verified_at"] = now()
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default="README.md", help="tracked file to mutate and restore")
    ap.add_argument("--drill-id", default=None)
    ap.add_argument("--append", default=None, help="drill log to append the record to")
    ap.add_argument("--verify", default=None, metavar="LOG", help="verify the last record in LOG")
    ap.add_argument("--as", dest="principal", default="", help="principal making the claim")
    args = ap.parse_args(argv)

    if args.verify:
        path = Path(args.verify)
        lines = [l for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
        if not lines:
            raise SystemExit(f"{path} has no records")
        record = verify(json.loads(lines[-1]), args.principal)
        lines[-1] = json.dumps(record)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"verified by {record['verifier']} at {record['verified_at']}")
        return 0

    drill_id = args.drill_id or f"DRILL-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    record = run_drill((ROOT / args.target).resolve(), drill_id)
    line = json.dumps(record)
    if args.append:
        with Path(args.append).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    print(line)
    print(
        f"\n{drill_id}: {record['outcome']}. `verifier` is empty and this script will not "
        f"fill it.\nThe provider will refuse this record until somebody who is not the "
        f"performer runs:\n  python scripts/rollback_drill.py --verify <log> --as <principal>",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
