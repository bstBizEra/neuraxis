"""ILR-001, pinned to the registry that enforces it.

The framework document carries the Capability-Authority Gate matrix (section
5.3) and the band assignment for every capability. Both are also in
`neuraxis.yaml`, which is the thing that actually denies.

Two copies of one rule is one rule and one liability. v0.1 of the document
additionally printed an inline copy of the registry YAML, which went stale
within three releases while still reading as authoritative -- the same failure
the document warns gate callers about. The YAML copy is gone; the matrix stays,
because it is what a reader needs, and these tests are the reason it is allowed
to stay.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from neuraxis import load_registry

DOC = pathlib.Path("docs/ILR-001-neuraxis.md")


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def reg():
    return load_registry()


def _matrix(text: str) -> dict[str, set[str]]:
    """Parse the section 5.3 table into {band: {controls}}."""
    section = text.split("### 5.3")[1].split("###")[0]
    rows = [ln for ln in section.splitlines() if ln.strip().startswith("| **BAND-")]
    assert rows, "the section 5.3 matrix has no band rows"
    header = next(ln for ln in section.splitlines() if "GV-01" in ln and "GV-10" in ln)
    controls = re.findall(r"GV-\d\d", header)
    out: dict[str, set[str]] = {}
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        band = re.search(r"BAND-[A-G]", cells[0]).group(0)
        marks = cells[1:]
        assert len(marks) == len(controls), f"{band}: {len(marks)} cells, {len(controls)} controls"
        out[band] = {c for c, m in zip(controls, marks) if m}
    return out


def test_the_matrix_in_the_document_is_the_matrix_in_the_registry(text, reg):
    """The one that would hurt.

    Section 5.3 is what a client, an auditor and an implementer all read. A band
    row that has drifted from the registry is a published claim about what
    licenses a capability, and it would be believed.
    """
    published = _matrix(text)
    shipped = {bid: set(band.requires) for bid, band in reg.bands.items()}
    assert published == shipped, {
        b: (published.get(b, set()) ^ shipped.get(b, set()))
        for b in set(published) | set(shipped)
        if published.get(b) != shipped.get(b)
    }


def test_every_capability_in_the_registry_appears_in_the_document(text, reg):
    for cap_id in reg.capabilities:
        assert re.search(rf"\b{re.escape(cap_id)}\b", text), f"{cap_id} is not in ILR-001"


def test_every_capability_is_listed_under_the_band_the_registry_assigns_it(text, reg):
    """A capability under the wrong heading is a wrong permission claim."""
    sections = {}
    for match in re.finditer(r"^### (BAND-[A-G]) .*$", text, re.M):
        body = text[match.end():]
        nxt = re.search(r"^### ", body, re.M)
        sections[match.group(1)] = body[: nxt.start()] if nxt else body
    for cap_id, cap in reg.capabilities.items():
        body = sections.get(cap.band, "")
        assert re.search(rf"\|\s*\*?\*?{re.escape(cap_id)}\*?\*?\s*\|", body), (
            f"{cap_id} belongs to {cap.band} in the registry and is not in that band's table"
        )


def test_the_document_does_not_print_a_copy_of_the_registry(text):
    """v0.1 did, and it was stale within three releases.

    A copy of a config inside a document goes stale silently and a reader trusts
    it -- exactly what the caller contract warns about, one layer up.
    """
    assert "framework: bst-neuraxis" not in text
    assert "on_missing_attestation:" not in text


_FENCE = re.compile(
    r"<!-- prohibited-examples -->.*?<!-- /prohibited-examples -->", re.S
)


def test_the_document_makes_no_ordinal_attainment_claim(text):
    """D-02's comms control, applied to the document that states it.

    The prohibition quotes the forbidden form in order to forbid it, so that
    one passage is fenced. The fence is counted as well as honoured: an
    exemption that can be added silently is an exemption that gets added.
    """
    assert len(_FENCE.findall(text)) == 1, "the ordinal-claim exemption has been widened"
    body = _FENCE.sub("", text)
    forbidden = re.findall(r"\b(?:at|reached|operating at) (?:level )?IL-\d\d\b", body)
    forbidden += re.findall(r"level \d+ of 33", body)
    assert not forbidden, forbidden


def test_the_split_is_recorded_not_the_relocation(text):
    """v0.1 relocated all of IL-13. D-01 split it, and the registry ships the split."""
    assert "IL-13a" in text and "IL-13b" in text
    assert "| IL-13 |" not in text, "the unsplit IL-13 still has a row"


def test_every_ruling_is_cited_somewhere(text):
    for ruling in ("D-01", "D-02", "D-03", "D-04", "D-05", "D-06", "D-07"):
        assert ruling in text, f"{ruling} amended this framework and is not cited in it"


def test_the_non_delegable_floor_in_the_document_matches_the_registry(text, reg):
    published = re.search(r"IL-31, IL-32, IL-33", text)
    assert published, "the non-delegable floor is not stated in the document"
    assert set(reg.non_delegable) == {"IL-31", "IL-32", "IL-33"}


def test_the_version_and_the_revision_history_agree(text):
    version = re.search(r"\| Version \| \*\*([\d.]+)\*\*", text).group(1)
    assert re.search(rf"^\| \*\*{re.escape(version)}\*\* \|", text, re.M), (
        f"version {version} has no revision-history row"
    )
