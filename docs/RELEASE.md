# Branching and release

**Status:** in force from v0.10.0. Enforced by the repository ruleset
`main: automation may propose, it may not merge` (no bypass actors).

---

## 1. Why there is a ruleset at all

The framework this repository implements says, in ILR-001 §6.4 and in every
`WAIT_FOR_AUTHORITY` verdict the gate issues: **automation may propose; it may
not merge.** Until now this package was developed by pushing directly to
`main` — which is that rule broken by the thing that defines it. It is the
process-layer form of `V = 0`: the performer merged its own work, with no
independent step between proposal and effect.

So the rule is now mechanical rather than stated:

| Rule | Why |
|---|---|
| Pull request required on `main` | The PR number is a ratification reference. A merge with no PR leaves no record that anything was reviewed, which is the property GV-07 is about |
| **0 required approvals** | A sole owner cannot approve their own pull request, so requiring 1 would deadlock every merge. This is ILR-001-DR D-06's shape again: two code owners is the control, one owner is the accepted risk, and a deadlock is not a stricter control — it is an outage that gets bypassed |
| All 7 status checks required | `ubuntu`/`windows` × `py3.11`/`py3.13`, the JS contract on both, and `gate denies by default`. CI is the independent verifier, and it is not the performer — NX-INV-2 holds at the process layer |
| Branch must be up to date before merge | A green check on a stale base proves nothing about what lands |
| No bypass actors | A bypass means a merge does not have to leave a record, which is the whole point |
| No force-push, no deletion | The history is the audit trail |

**What this does not claim.** One person opening and merging their own pull
request is weaker than two-person review. It is not theatre either: the change
is visible as a diff before it lands, CI runs on the merge result rather than
on the author's machine, and the PR is a durable reference an auditor can
follow. When a second collaborator exists, raise the approval count to 1 and
this section gets shorter.

**`require_extra_approval_for_unattributed_changes` is off**, deliberately.
GitHub turns it on by default; with 0 required approvals and a single owner it
is an unsatisfiable condition, and an unsatisfiable rule is an outage waiting
for a bypass. Commits carrying a `Co-Authored-By:` trailer for an address not
linked to a GitHub account are the common case here.

---

## 2. The flow for a change

```bash
git switch -c v0.10.0-<short-name>          # or fix/<what>, docs/<what>
# ... work, with the suite green locally ...
git push -u origin v0.10.0-<short-name>
gh pr create --fill
# CI runs. When all seven checks are green:
gh pr merge --squash --delete-branch
```

One branch per task, short-lived, deleted on merge. No `develop`, no release
branches, no long-running integration branch — the governing constraint is
still *one task at a time, CI green = done*, and a branching model with more
states than that has more states than the work does.

Branch naming is a convention, not a rule: `v<version>-<name>` for work that
ships a version, `fix/<what>` and `docs/<what>` otherwise.

---

## 3. Cutting a release

A release is a tag. The version lives in exactly two places and both must
agree with the tag:

```bash
# on the branch, as part of the change:
#   pyproject.toml          version = "0.10.0"
#   src/neuraxis/__init__.py __version__ = "0.10.0"
# `neuraxis contract` emits __version__, so the JS client sees it too.

gh pr merge --squash --delete-branch
git switch main && git pull
git tag -a v0.10.0 -m "v0.10.0 - <one line>"
git push origin v0.10.0
```

Pushing the tag runs `.github/workflows/release.yml`, which:

1. checks out the **tag**, not the branch it came from;
2. runs the full suite and the gate self-check against that exact commit;
3. builds an sdist and a wheel;
4. records the SHA-256 of `src/neuraxis/config/neuraxis.yaml` and the output of
   `neuraxis validate --json`;
5. creates a GitHub Release with all four as assets.

### Why the registry digest ships with the release

The registry is **kernel** under KBS-001 (K-04 family). The roadmap's weekly
job is a drift check of the registry against its *ratified* version — and that
sentence is meaningless while no version is ratified. The digest in the release
is what makes it a real comparison:

```bash
sha256sum src/neuraxis/config/neuraxis.yaml
# compare against REGISTRY-DIGEST.txt from the release for the version you claim to run
```

A mismatch is not automatically an incident. It means the kernel config on disk
is not the one that was released, which is either an unratified change or a
version you did not think you were running. Both are worth knowing at 02:00.

### Tags that predate this workflow

`v0.3.1` through `v0.9.0` were tagged retroactively, after the fact, from the
commits that shipped them. A tag-push trigger uses the workflow file as it
existed at the tagged commit, so none of them produced a release. To build one
for an older tag:

```bash
gh workflow run release.yml -f tag=v0.9.0
```

Note the honest gap: `v0.1` through `v0.3` were developed before this
repository existed and landed inside the initial commit. They have no tags and
cannot get one. `v0.3.1` is the first independently referenceable version.

---

## 4. What this does not solve

The ruleset constrains writes to `main` through GitHub's API. It does not
authenticate the *author* of anything: commit signing is not required, the
`Co-Authored-By` trailer is a string, and a release asset is whatever the
workflow built. It is the same limit as everywhere else in this package — the
substrate is unauthenticated until KBS-001 T1 issues real identities and a
kernel write path.

What it does do is make the process rule fail closed instead of relying on
whoever is in a hurry remembering it. That is the difference between a control
and a preference, and it is the only kind of difference this project counts.
