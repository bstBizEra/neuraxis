"""The ratification-gap check (scripts/ratification_gap.py).

The check exists because three versions shipped past the last release and
nothing said so. Its own first run then reported "ratification is current" on
that very repository, because it consulted `git tag --list` and this machine
held three tags it had never managed to push. It went green on its own subject.

So the test that matters here is not "does it count versions" — it is
`test_a_local_tag_does_not_ratify_anything`, which fails on that first design
and passes on the one that ships. Everything else is the four-rule provider
contract applied to a script: fail closed, positive control, vacuity probe,
cite what it found.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ratification_gap.py"
NOW = "2026-09-22T12:00:00+00:00"


def _load():
    spec = importlib.util.spec_from_file_location("ratification_gap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path):
    """A throwaway repository whose pyproject.toml can be walked forward."""

    def git(*args: str, check: bool = True) -> str:
        try:
            done = subprocess.run(
                ["git", "-C", str(tmp_path), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pytest.skip("git is not available")
        if check and done.returncode != 0:
            pytest.skip(f"git {args[0]} failed in this environment")
        return done.stdout

    git("init", "--quiet")
    git("config", "user.email", "suite@example.invalid")
    git("config", "user.name", "suite")

    def bump(version: str, *, when: str) -> None:
        (tmp_path / "pyproject.toml").write_text(
            f'[project]\nname = "thing"\nversion = "{version}"\n', encoding="utf-8"
        )
        git("add", "-A")
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "--quiet", "-m", f"v{version}"],
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": str(tmp_path),
                "GIT_AUTHOR_DATE": when,
                "GIT_COMMITTER_DATE": when,
                "GIT_AUTHOR_NAME": "suite",
                "GIT_AUTHOR_EMAIL": "suite@example.invalid",
                "GIT_COMMITTER_NAME": "suite",
                "GIT_COMMITTER_EMAIL": "suite@example.invalid",
            },
            capture_output=True,
            check=False,
        )

    return SimpleNamespace(path=tmp_path, git=git, bump=bump)


def run(module, repo, *args: str) -> tuple[int, str]:
    path = repo.path if hasattr(repo, "path") else repo
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = module.main(["--repo", str(path), "--now", NOW, *args])
    return code, buffer.getvalue()


@pytest.fixture
def module():
    return _load()


# --- the regression the real run produced -----------------------------------


def test_a_local_tag_does_not_ratify_anything(module, repo):
    """The bug that shipped in the first draft, pinned.

    A tag that was never pushed publishes no release and no digest. If this
    check ever consults tags again, this fails — which is the only way the
    defect announces itself, since it manifests as silence.
    """
    repo.bump("0.19.0", when="2026-09-01T00:00:00+0000")
    repo.bump("0.20.0", when="2026-09-02T00:00:00+0000")
    repo.git("tag", "v0.20.0")  # created locally, never pushed

    code, out = run(module, repo, "--released", "v0.19.0")
    assert "v0.20.0" in out, "an unpushed tag was treated as ratification"
    assert "1 version(s) shipped since then with no release" in out
    # 20 days past the bump, so it is also outside the grace window. The first
    # design returned EXIT_OK here with an empty report, which is the failure:
    # silence that reads as health.
    assert code == module.EXIT_STALE


# --- what it finds ----------------------------------------------------------


def test_it_names_every_version_past_the_release(module, repo):
    for n, day in ((19, "01"), (20, "02"), (21, "03"), (22, "04")):
        repo.bump(f"0.{n}.0", when=f"2026-09-{day}T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.19.0")
    for version in ("v0.20.0", "v0.21.0", "v0.22.0"):
        assert version in out
    assert "v0.19.0  bumped" not in out, "the released version is not itself a gap"


def test_the_gap_ages_from_the_oldest_not_the_newest(module, repo):
    """Ratification went stale when the FIRST version passed the release.

    Measuring from the newest bump would reset the clock on every release, so
    a process that has stopped tagging would never age past a few days.
    """
    repo.bump("0.19.0", when="2026-08-01T00:00:00+0000")
    repo.bump("0.20.0", when="2026-08-02T00:00:00+0000")
    repo.bump("0.21.0", when="2026-09-21T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.19.0")
    assert code == module.EXIT_STALE
    assert "v0.20.0 has been unratified for 51d" in out


def test_inside_the_grace_window_it_warns_and_passes(module, repo):
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    repo.bump("0.20.0", when="2026-09-21T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.19.0")
    assert code == module.EXIT_OK
    assert "::warning::" in out
    assert "push the tags before it closes" in out


def test_strict_fails_on_any_gap(module, repo):
    """Mirrors drift.yml's own `strict` input rather than inventing a second
    vocabulary for the same idea."""
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    repo.bump("0.20.0", when="2026-09-21T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.19.0", "--strict")
    assert code == module.EXIT_STALE
    assert "strict mode" in out


# --- positive control -------------------------------------------------------


def test_a_current_release_reports_current(module, repo):
    """Vacuity probe. A check that always found a gap would be switched off."""
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    repo.bump("0.20.0", when="2026-09-21T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.20.0")
    assert code == module.EXIT_OK
    assert "ratification is current" in out
    assert "::warning::" not in out and "::error::" not in out


def test_a_version_older_than_the_release_is_history_not_a_gap(module, repo):
    """Tagging it now would ratify backwards, so it is not something to chase."""
    repo.bump("0.18.0", when="2026-09-01T00:00:00+0000")
    repo.bump("0.19.0", when="2026-09-02T00:00:00+0000")

    code, out = run(module, repo, "--released", "v0.19.0")
    assert code == module.EXIT_OK
    assert "v0.18.0" not in out


# --- ordering ---------------------------------------------------------------


def test_versions_are_compared_numerically_not_lexically(module):
    """Lexically, "0.9.0" > "0.10.0", which ratifies backwards."""
    assert module.parse_version("0.9.0") < module.parse_version("0.10.0")
    assert module.parse_version("0.22.0") > module.parse_version("0.9.0")


# --- fail closed ------------------------------------------------------------


def test_an_unreadable_repository_cannot_run_rather_than_reporting_clean(module, tmp_path):
    """The failure that would matter: a check that says nothing is stale
    because it could not look."""
    code, out = run(module, tmp_path / "not-a-repo", "--released", "v0.19.0")
    assert code == module.EXIT_CANNOT_RUN
    assert "could not run" in out
    assert "ratification is current" not in out


def test_a_malformed_release_argument_cannot_run(module, repo):
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    code, out = run(module, repo, "--released", "vNOPE")
    assert code == module.EXIT_CANNOT_RUN


def test_a_naive_clock_is_refused(module, repo):
    """Ordering across absent offsets is not decidable — the same rule the
    providers apply to evidence timestamps."""
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    code = module.main(
        ["--repo", str(repo.path), "--now", "2026-09-22T12:00:00", "--released", "v0.19.0"]
    )
    assert code == module.EXIT_CANNOT_RUN


def test_a_negative_grace_window_is_refused(module, repo):
    repo.bump("0.19.0", when="2026-09-20T00:00:00+0000")
    code, _ = run(module, repo, "--released", "v0.19.0", "--grace-days", "-1")
    assert code == module.EXIT_CANNOT_RUN


def test_no_release_at_all_reports_every_version_as_unratified(module, repo):
    """`gh release list` returns empty on a repository that has never released.
    Treating that as 'current' would be the fail-open reading."""
    repo.bump("0.1.0", when="2026-09-01T00:00:00+0000")
    code, out = run(module, repo)
    assert "v0.1.0" in out
    assert "<no release>" in out
