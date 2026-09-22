#!/usr/bin/env python3
"""How stale is the version the drift check compares against?

KBS-001 K-09 asks whether the kernel registry on disk is the ratified one.
`.github/workflows/drift.yml` answers it by fetching the digest from the latest
release. What neither asks is whether *that release* is still a reasonable
thing to compare against.

On 2026-09-22 this repository was at v0.22.0 and the newest tag on the remote
was v0.19.0. Three versions had shipped without ever being ratified, because
the tag push returns 403 on credential scope and nothing downstream noticed.
The drift job kept running, kept passing, and kept reporting against a baseline
five days and three versions old. Had the kernel changed in that window, the
job would have printed "the kernel registry has moved since v0.19.0" — true,
and read by anybody as "v0.19.0 is what we released", which it was not.

That is the same defect the version claims in README and RUNBOOK had, one
level up: a fact nobody checks drifts until it is wrong, then stays wrong
quietly. So the drift job now states the age of its own reference.

WHAT IT REPORTS. Every version that appeared in pyproject.toml on this branch
and is newer than the released one, plus the age of the oldest, because that is
when ratification actually went stale. Tags are deliberately not consulted; see
`unratified` for the run that proved why.

WHY AGE AND NOT COUNT. Three unratified versions cut in one afternoon is a
normal working day; one unratified version sitting for a month is a release
process that has quietly stopped. A count cannot tell those apart. The grace
window mirrors drift.yml's existing rule for the kernel — 7 days, the window
the registry itself uses for config-driven controls — because two different
staleness rules on the same job would be a rule nobody can state.

Exit codes follow the drift job's convention:

    0   the released version is current, or the gap is inside the grace window
    10  the gap is older than the grace window
    2   the check could not run (bad arguments, no git, unreadable history)

2 rather than 0 on an internal failure: a staleness check that cannot read the
history has not established that nothing is stale.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: `version = "0.22.0"` in pyproject.toml. Anchored to the line start so a
#: version pin inside a dependency specifier is not mistaken for the package's.
VERSION_LINE = re.compile(r'^version\s*=\s*"([0-9]+(?:\.[0-9]+)*)"', re.M)

EXIT_OK = 0
EXIT_STALE = 10
EXIT_CANNOT_RUN = 2


class CannotRun(Exception):
    """The check could not be performed. Never reported as 'nothing is stale'."""


def parse_version(text: str) -> tuple[int, ...]:
    """`0.22.0` -> (0, 22, 0). Comparison is numeric, never lexical.

    Lexical ordering says v0.9.0 is newer than v0.10.0, which is how a release
    process ends up ratifying backwards.
    """
    return tuple(int(part) for part in text.split("."))


def normalise(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def git(*args: str, repo: Path) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"git could not be run: {exc}") from exc
    if done.returncode != 0:
        raise CannotRun(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def version_history(repo: Path, *, path: str = "pyproject.toml") -> list[tuple[str, datetime]]:
    """Every distinct package version in this branch's history, oldest first.

    Read from the file's own history rather than from tags, because the point
    of the check is to find versions that were shipped and never tagged. Asking
    the tags would only ever report the tags that exist.
    """
    log = git("log", "--format=%H %cI", "--reverse", "--", path, repo=repo)
    seen: dict[str, datetime] = {}
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, _, when = line.partition(" ")
        try:
            content = git("show", f"{sha}:{path}", repo=repo)
        except CannotRun:
            # The file did not exist at that commit, or was deleted in it.
            continue
        found = VERSION_LINE.search(content)
        if not found:
            continue
        version = found.group(1)
        if version not in seen:
            seen[version] = datetime.fromisoformat(when)
    return sorted(seen.items(), key=lambda pair: pair[1])


def unratified(
    repo: Path,
    *,
    released: str | None,
    path: str = "pyproject.toml",
) -> list[tuple[str, datetime]]:
    """Versions newer than `released`, oldest first.

    THE FIRST VERSION OF THIS FUNCTION ALSO CONSULTED `git tag --list`, on the
    reasoning that a tagged version is not a missing tag. Run against this
    repository it printed "ratification is current" — while the remote's newest
    tag was v0.19.0 and three versions had shipped past it. The three tags
    existed locally and had never been pushed, which is the exact condition the
    check was written to detect. It went green on its own subject.

    So tags are not consulted at all. Ratification is a published release
    carrying REGISTRY-DIGEST.txt; a tag that reaches nobody ratifies nothing,
    and a local tag is not even evidence that a tag exists. `released` is the
    single input, and it is the same value the drift job already compares the
    kernel against — one source, so the two answers cannot disagree.
    """
    floor = parse_version(normalise(released)) if released else ()
    gap = []
    for version, when in version_history(repo, path=path):
        if floor and parse_version(version) <= floor:
            # At or below what is already ratified. Tagging it now would ratify
            # backwards, so it is history rather than a gap.
            continue
        gap.append((version, when))
    return gap


def report(
    gap: list[tuple[str, datetime]],
    *,
    released: str | None,
    grace_days: int,
    now: datetime,
    strict: bool = False,
) -> int:
    if not gap:
        current = released or "nothing"
        print(
            f"ratification is current: the released version is {current} "
            "and no newer version has shipped"
        )
        return EXIT_OK

    oldest_version, oldest_when = gap[0]
    age_days = (now - oldest_when).days

    print(f"the drift check compares the kernel against {released or '<no release>'}")
    print(f"{len(gap)} version(s) shipped since then with no release, so nothing ratifies them:")
    for version, when in gap:
        print(f"  v{version}  bumped {when.date().isoformat()}  ({(now - when).days}d ago)")

    if strict or age_days > grace_days:
        why = "strict mode" if strict and age_days <= grace_days else f"grace {grace_days}d"
        print(
            f"::error::v{oldest_version} has been unratified for {age_days}d ({why}). "
            f"Push the tags, or the drift check is measuring the kernel against a "
            f"baseline {len(gap)} release(s) old."
        )
        return EXIT_STALE

    print(
        f"::warning::the newest ratified version is {released or '<none>'}, "
        f"{len(gap)} behind the package. Oldest gap is {age_days}d, inside the "
        f"{grace_days}d grace window; push the tags before it closes."
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--released", help="the latest released tag, e.g. v0.19.0")
    parser.add_argument("--repo", default=str(ROOT), help="repository to inspect")
    parser.add_argument("--grace-days", type=int, default=7)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on any unratified version, not only one older than the grace window",
    )
    parser.add_argument("--path", default="pyproject.toml")
    parser.add_argument("--now", help="override the clock (ISO-8601, for tests)")
    args = parser.parse_args(argv)

    try:
        if args.grace_days < 0:
            raise CannotRun("--grace-days cannot be negative")
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise CannotRun("--now needs a timezone offset")
        if args.released:
            parse_version(normalise(args.released))
        gap = unratified(Path(args.repo), released=args.released, path=args.path)
    except CannotRun as exc:
        print(f"::error::ratification gap check could not run: {exc}")
        return EXIT_CANNOT_RUN
    except ValueError as exc:
        print(f"::error::ratification gap check could not run: {exc}")
        return EXIT_CANNOT_RUN

    return report(
        gap,
        released=args.released,
        grace_days=args.grace_days,
        now=now,
        strict=args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
