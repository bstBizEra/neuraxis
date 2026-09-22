#!/usr/bin/env python3
"""A per-file coverage floor, because `fail_under` is an average.

`fail_under = 90` passed for weeks while scripts/rollback_drill.py — the file
that produces GV-05's evidence and refuses to sign its own work — sat at 61%
with its entire main() untested. Nothing lied. The total really was 93%. The
average simply cannot see a single file being abandoned, and the file most
worth watching is rarely the one carrying the statement count.

That is the same shape as every other defect this repository has found: a
measurement that is true, reported faithfully, and answering a question nobody
meant to ask.

WHY THE FLOOR IS BELOW THE AGGREGATE. 85%, against an aggregate of 90%. A
per-file floor set at the current worst file (89.80%) would fire on the first
refactor that momentarily dips, and a check that fires on noise gets raised
until it means nothing. This is a floor against a file being ABANDONED, not a
second attempt at the aggregate target. It would have caught rollback_drill.py
at 61% on the day it landed, which is the whole requirement.

STALENESS. The report is read from disk, so it can be old — and a check that
reads yesterday's artefact reports yesterday's health in today's voice. That
was the exact defect in the drift baseline. So a report older than --max-age
minutes is refused rather than trusted.

Exit codes follow the convention used by drift.yml and ratification_gap.py:

    0   every file is at or above the floor
    10  at least one file is below it
    2   the check could not run (missing, malformed or stale report)

2 rather than 0, because a floor check that could not read the report has not
established that nothing is below the floor.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_BELOW = 10
EXIT_CANNOT_RUN = 2


class CannotRun(Exception):
    """The check could not be performed. Never reported as 'nothing is below'."""


def load(path: Path, *, max_age: timedelta | None, now: datetime) -> dict:
    if not path.is_file():
        raise CannotRun(f"no coverage report at {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise CannotRun(f"{path} has no 'files' section; is it a coverage json report?")
    if not report["files"]:
        # An empty report is not "every file passes". It is no measurement.
        raise CannotRun(f"{path} covers no files at all")

    if max_age is not None:
        stamp = (report.get("meta") or {}).get("timestamp")
        if not stamp:
            raise CannotRun(f"{path} carries no meta.timestamp, so its age cannot be checked")
        try:
            written = datetime.fromisoformat(stamp)
        except ValueError as exc:
            raise CannotRun(f"{path}: meta.timestamp is not ISO-8601 ({stamp!r})") from exc
        if written.tzinfo is None:
            # coverage.py writes a naive local timestamp. Compare in the same
            # frame rather than guessing an offset, and never silently treat a
            # naive value as UTC.
            reference = now.astimezone().replace(tzinfo=None)
        else:
            reference = now
        age = reference - written
        if age > max_age:
            raise CannotRun(
                f"{path} was written {age} ago (max {max_age}); it describes an "
                "older run than this one. Re-run the suite with --cov-report=json."
            )
    return report


def below_floor(report: dict, *, floor: float) -> list[tuple[str, float]]:
    found = [
        (name, data["summary"]["percent_covered"])
        for name, data in sorted(report["files"].items())
        if data["summary"]["percent_covered"] < floor
    ]
    return sorted(found, key=lambda pair: pair[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", default="coverage.json")
    ap.add_argument("--floor", type=float, default=85.0)
    ap.add_argument(
        "--max-age-minutes",
        type=float,
        default=60.0,
        help="refuse a report older than this; 0 disables the staleness check",
    )
    ap.add_argument("--now", help="override the clock (ISO-8601, for tests)")
    args = ap.parse_args(argv)

    try:
        if not 0 < args.floor <= 100:
            raise CannotRun(f"--floor must be within (0, 100], got {args.floor}")
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
        max_age = (
            timedelta(minutes=args.max_age_minutes) if args.max_age_minutes > 0 else None
        )
        report = load(Path(args.report), max_age=max_age, now=now)
        under = below_floor(report, floor=args.floor)
    except CannotRun as exc:
        print(f"::error::the per-file coverage floor could not run: {exc}")
        return EXIT_CANNOT_RUN

    measured = len(report["files"])
    if not under:
        worst = min(d["summary"]["percent_covered"] for d in report["files"].values())
        print(
            f"per-file floor {args.floor:g}%: all {measured} file(s) at or above it "
            f"(worst {worst:.2f}%)"
        )
        return EXIT_OK

    print(f"{len(under)} of {measured} file(s) below the {args.floor:g}% per-file floor:")
    for name, pct in under:
        print(f"  {pct:6.2f}%  {name}")
    print(
        "::error::a file below the per-file floor is one the aggregate cannot see. "
        "Test it, or argue in a diff for why it should not be."
    )
    return EXIT_BELOW


if __name__ == "__main__":
    raise SystemExit(main())
