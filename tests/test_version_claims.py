"""Every place this package states its own version must state the same one.

`docs/RELEASE.md` §3 says the version lives in exactly two places and both must
agree with the tag. That was true of the two places it names and false of the
two it does not: at v0.21.0 the README was still announcing v0.7.0 and the
runbook still said v0.10.0. Fifteen releases and twelve releases stale
respectively, and nothing noticed, because a version claim in prose is checked
by whoever happens to reread the paragraph.

The runbook one is not cosmetic. It is the first line of the document somebody
reads while holding the pager, and it tells them which package they are
debugging.

So the rule that was already written down is now a test. This is the same move
the rest of the repository makes: a claim nothing checks is a claim that drifts
until it is wrong, and then stays wrong quietly.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from neuraxis import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Each place that states the package's own version, and the pattern that
#: finds it. A new one added without a line here is exactly the drift this
#: file exists to catch, which is why the patterns are narrow: they match the
#: version claim and nothing else on the page.
CLAIMS = {
    "README.md": re.compile(r"Reference implementation of ILR-001\. \*\*v([\d.]+)\.\*\*"),
    "docs/RUNBOOK.md": re.compile(r"\*\*Package:\*\* `neuraxis` v([\d.]+)\."),
}


@pytest.mark.parametrize("relative", sorted(CLAIMS))
def test_a_documents_version_claim_matches_the_package(relative):
    text = (REPO_ROOT / relative).read_text(encoding="utf-8-sig")
    found = CLAIMS[relative].search(text)
    assert found, f"{relative}: the version claim this test pins is gone or reworded"
    assert found.group(1) == __version__, (
        f"{relative} claims v{found.group(1)}, the package is v{__version__}"
    )


def test_pyproject_and_dunder_version_agree():
    """The two places docs/RELEASE.md §3 already named.

    The third consumer, `neuraxis contract` — what the JS client reads — is
    pinned to `__version__` in tests/test_contract.py. It is not re-asserted
    here: a second copy of that check would pass whether or not the contract
    still emits anything, and a check that cannot fail is the thing this
    package refuses everywhere else.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8-sig"))
    assert pyproject["project"]["version"] == __version__
