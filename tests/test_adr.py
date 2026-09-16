"""The ADR log, held to its own rule.

An ADR index that has drifted from the files beside it is worse than no index:
it is a table of contents people trust. These are cheap checks that keep the
log a log rather than a folder.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ADR_DIR = pathlib.Path("docs/adr")
INDEX = ADR_DIR / "README.md"


def _adrs() -> list[pathlib.Path]:
    return sorted(p for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def test_there_are_adrs_at_all():
    assert _adrs(), "the ADR directory is empty"


@pytest.mark.parametrize("adr", _adrs(), ids=lambda p: p.stem)
def test_every_adr_states_its_status_and_how_it_could_be_wrong(adr):
    """A decision with no stated way to be wrong is a belief.

    The register makes the same demand of its own rulings, and the index says
    so out loud, so the log should be held to it.
    """
    text = adr.read_text(encoding="utf-8")
    assert re.search(r"^\*\*Status:\*\*", text, re.M), "no Status line"
    assert re.search(r"^## Reversal", text, re.M), "no Reversal section"
    assert re.search(r"^## Decision", text, re.M), "no Decision section"
    assert re.search(r"^## Consequences", text, re.M), "no Consequences section"


def test_every_adr_is_listed_in_the_index():
    listed = set(re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", INDEX.read_text(encoding="utf-8")))
    on_disk = {p.name for p in _adrs()}
    assert on_disk == listed, f"index and directory disagree: {on_disk ^ listed}"


def test_every_link_between_adrs_resolves():
    """Relative links inside the log, including the cross-references."""
    for source in [INDEX, *_adrs()]:
        for target in re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", source.read_text(encoding="utf-8")):
            assert (ADR_DIR / target).exists(), f"{source.name} links to missing {target}"


def test_adr_numbers_are_contiguous_from_one():
    numbers = [int(p.name[:4]) for p in _adrs()]
    assert numbers == list(range(1, len(numbers) + 1)), f"gap or duplicate in {numbers}"
