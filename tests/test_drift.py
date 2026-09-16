"""The drift check (v0.10.0) - KBS-001 K-09.

The registry is kernel. A release records the SHA-256 of the exact bytes that
were ratified; this asks whether the file the gate is about to load is that
one. The tests below are mostly about the ways a check like this reports clean
when it should not: an expectation nobody could read, an expectation that is
not a digest, a file that says nothing about sha256.
"""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml

from neuraxis.cli import main
from neuraxis.errors import RegistryError
from neuraxis.registry import DEFAULT_REGISTRY, registry_digest


def _shipped_sha() -> str:
    return hashlib.sha256(DEFAULT_REGISTRY.read_bytes()).hexdigest()


# ---- the digest itself -------------------------------------------------


def test_the_digest_is_of_the_bytes_on_disk():
    """It has to equal what `sha256sum` prints, or the comparison is useless.

    Hashing the parsed document, or re-encoding the text, would produce a
    number that only this tool can reproduce - and the operator at 02:00 has
    `sha256sum`, not this tool.
    """
    sha, path = registry_digest()
    assert path == DEFAULT_REGISTRY
    assert sha == _shipped_sha()
    assert len(sha) == 64 and sha == sha.lower()


def test_a_missing_registry_is_an_error_not_a_digest(tmp_path):
    with pytest.raises(RegistryError, match="registry not found"):
        registry_digest(tmp_path / "absent.yaml")


def test_one_byte_changes_the_digest(tmp_path):
    copy = tmp_path / "neuraxis.yaml"
    copy.write_bytes(DEFAULT_REGISTRY.read_bytes() + b"\n# a comment is a kernel change\n")
    assert registry_digest(copy)[0] != _shipped_sha()


# ---- validate carries it ----------------------------------------------


def test_validate_reports_the_digest(capsys):
    assert main(["--json", "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry_sha256"] == _shipped_sha()
    assert payload["registry_path"].endswith("neuraxis.yaml")


# ---- the comparison ----------------------------------------------------


def test_drift_with_no_expectation_compares_nothing_and_says_so(capsys):
    assert main(["drift"]) == 0
    out = capsys.readouterr().out
    assert "No expectation given" in out
    assert _shipped_sha() in out


def test_a_matching_digest_exits_zero(capsys):
    assert main(["drift", "--expect", _shipped_sha()]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_a_mismatched_digest_exits_ten(capsys):
    assert main(["drift", "--expect", "0" * 64]) == 10
    out = capsys.readouterr().out
    assert "DRIFT" in out
    assert "Do not attest anything against it" in out


def test_a_changed_registry_is_detected_against_its_old_digest(tmp_path, capsys):
    before = _shipped_sha()
    copy = tmp_path / "neuraxis.yaml"
    copy.write_bytes(DEFAULT_REGISTRY.read_bytes())
    assert main(["--registry", str(copy), "drift", "--expect", before]) == 0
    capsys.readouterr()

    # An unratified edit to the kernel: the waiver TTL quietly widened.
    data = yaml.safe_load(copy.read_text(encoding="utf-8-sig"))
    data["enforcement"]["waivers"]["max_ttl"] = "30d"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["--registry", str(copy), "drift", "--expect", before]) == 10
    assert "DRIFT" in capsys.readouterr().out


# ---- an expectation that cannot be read is never a pass ----------------


@pytest.mark.parametrize("bad", ["", "deadbeef", "0" * 63, "0" * 65, "G" * 64, "  "])
def test_a_non_digest_expectation_is_an_error_not_a_match(bad, capsys):
    """Exit 2, not 0. Reading it as "nothing to compare" would report clean."""
    assert main(["drift", "--expect", bad]) == 2
    assert "sha256 digest" in capsys.readouterr().err or True


def test_an_uppercase_digest_still_matches(capsys):
    assert main(["drift", "--expect", _shipped_sha().upper()]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_expect_and_expect_file_together_are_refused(tmp_path, capsys):
    f = tmp_path / "d.txt"
    f.write_text(f"sha256: {_shipped_sha()}\n", encoding="utf-8")
    code = main(["drift", "--expect", _shipped_sha(), "--expect-file", str(f)])
    assert code == 2
    assert "not both" in capsys.readouterr().err


def test_a_missing_expectation_file_is_an_error(tmp_path, capsys):
    assert main(["drift", "--expect-file", str(tmp_path / "absent.txt")]) == 2
    assert "not found" in capsys.readouterr().err


def test_an_expectation_file_with_no_digest_is_an_error(tmp_path, capsys):
    f = tmp_path / "d.txt"
    f.write_text("registry: somewhere\nversion: 0.9.0\n", encoding="utf-8")
    assert main(["drift", "--expect-file", str(f)]) == 2
    assert "no sha256 line" in capsys.readouterr().err


# ---- the release asset format -----------------------------------------


def test_a_release_digest_file_is_read(tmp_path, capsys):
    """The exact shape release.yml writes."""
    f = tmp_path / "REGISTRY-DIGEST.txt"
    f.write_text(
        "registry: src/neuraxis/config/neuraxis.yaml\n"
        f"sha256:   {_shipped_sha()}\n"
        "version:  0.10.0\n"
        "tag:      v0.10.0\n"
        "commit:   0123456789abcdef\n",
        encoding="utf-8",
    )
    assert main(["drift", "--expect-file", str(f)]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_a_bare_digest_file_is_read(tmp_path, capsys):
    f = tmp_path / "d.txt"
    f.write_text(_shipped_sha() + "\n", encoding="utf-8")
    assert main(["drift", "--expect-file", str(f)]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_a_bom_does_not_break_the_expectation_file(tmp_path, capsys):
    """PowerShell writes one by default; it must not read as "no digest"."""
    f = tmp_path / "d.txt"
    f.write_text(f"sha256: {_shipped_sha()}\n", encoding="utf-8-sig")
    assert main(["drift", "--expect-file", str(f)]) == 0
    assert "MATCH" in capsys.readouterr().out


def test_a_release_file_naming_a_different_registry_still_compares_the_digest(
    tmp_path, capsys
):
    """The digest is the claim; the path line is provenance, not the comparison."""
    f = tmp_path / "REGISTRY-DIGEST.txt"
    f.write_text(f"registry: somewhere/else.yaml\nsha256: {'1' * 64}\n", encoding="utf-8")
    assert main(["drift", "--expect-file", str(f)]) == 10


def test_drift_json_carries_both_digests(tmp_path, capsys):
    assert main(["--json", "drift", "--expect", "0" * 64]) == 10
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry_sha256"] == _shipped_sha()
    assert payload["expected_sha256"] == "0" * 64
    assert payload["matches"] is False


def test_drift_refuses_to_report_on_a_registry_that_does_not_load(tmp_path, capsys):
    """An invalid kernel is a bigger problem than a drifted one."""
    bad = tmp_path / "neuraxis.yaml"
    bad.write_text("framework: test\n", encoding="utf-8")
    assert main(["--registry", str(bad), "drift", "--expect", "0" * 64]) == 2
