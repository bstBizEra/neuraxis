from __future__ import annotations

from datetime import timedelta

import pytest
import yaml

from neuraxis import load_registry
from neuraxis.errors import CycleError, RegistryError, UnknownCapabilityError, UnknownControlError
from neuraxis.registry import parse_duration


def _write(tmp_path, data):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _minimal():
    return {
        "framework": "test",
        "version": "0.1",
        "governance": {"GV-01": {"name": "identity", "attestation": "x/y"}},
        "capabilities": {"IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"}},
        "bands": {"BAND-A": {"requires": ["GV-01"], "depends_on": []}},
        "authority": {"role_grants": {"operator": ["BAND-A"]}},
        "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "24h"},
    }


def test_bundled_registry_loads_and_is_internally_consistent(registry):
    assert registry.framework == "bst-neuraxis"
    assert len(registry.capabilities) == 34   # 33 ILs, with IL-13 split by D-01
    assert len(registry.bands) == 7
    assert len(registry.controls) == 10
    for cap in registry.capabilities.values():
        assert cap.band in registry.bands
    for band in registry.bands.values():
        for control in band.requires:
            assert control in registry.controls


def test_il_13_is_split_by_d01(registry):
    """The ILR-001 correction, as ILR-001-DR D-01 refines it.

    Self-modification stays in BAND-G. Envelope-bounded self-tuning is
    admissible from BAND-C, because a rule forbidding parameter adjustment
    outright gets reclassified as "configuration" and done out of view.
    """
    assert registry.capability("IL-13b").band == "BAND-G"
    assert registry.capability("IL-13a").band == "BAND-C"
    assert registry.capability("IL-13a").envelope_bounded is True
    assert registry.capability("IL-13b").envelope_bounded is False
    assert "IL-13" not in registry.capabilities


def test_band_g_requires_every_governance_control(registry):
    """Freedom costs all ten controls; Band A costs two."""
    assert set(registry.band("BAND-G").requires) == set(registry.controls)
    assert set(registry.band("BAND-A").requires) == {"GV-01", "GV-03"}


def test_band_requirements_are_monotonic_along_dependencies(registry):
    """A band never requires fewer controls than a band it depends on."""
    for band in registry.bands.values():
        for dep in band.depends_on:
            assert set(registry.band(dep).requires) <= set(band.requires), (
                f"{band.id} requires fewer controls than its prerequisite {dep}"
            )


def test_band_closure_is_dependency_ordered(registry):
    closure = registry.band_closure("BAND-G")
    assert closure[-1] == "BAND-G"
    assert closure.index("BAND-A") < closure.index("BAND-B")
    assert closure.index("BAND-F") < closure.index("BAND-G")


def test_unknown_capability_raises(registry):
    with pytest.raises(UnknownCapabilityError):
        registry.capability("IL-99")


def test_missing_file_raises(tmp_path):
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "absent.yaml")


def test_invalid_yaml_raises(tmp_path):
    path = tmp_path / "neuraxis.yaml"
    path.write_text("framework: [unclosed", encoding="utf-8")
    with pytest.raises(RegistryError, match="not valid YAML"):
        load_registry(path)


def test_band_requiring_undefined_control_raises(tmp_path):
    data = _minimal()
    data["bands"]["BAND-A"]["requires"] = ["GV-99"]
    with pytest.raises(UnknownControlError):
        load_registry(_write(tmp_path, data))


def test_capability_in_undefined_band_raises(tmp_path):
    data = _minimal()
    data["capabilities"]["IL-02"] = {"name": "x", "band": "BAND-Z", "question": "?"}
    with pytest.raises(RegistryError, match="undefined band"):
        load_registry(_write(tmp_path, data))


def test_dependency_cycle_is_detected(tmp_path):
    data = _minimal()
    data["capabilities"]["IL-02"] = {"name": "x", "band": "BAND-B", "question": "?"}
    data["bands"]["BAND-A"]["depends_on"] = ["BAND-B"]
    data["bands"]["BAND-B"] = {"requires": ["GV-01"], "depends_on": ["BAND-A"]}
    with pytest.raises(CycleError):
        load_registry(_write(tmp_path, data))


def test_registry_permitting_allow_on_missing_attestation_is_rejected(tmp_path):
    """NX-INV-1 is not configurable. A fail-open registry is not a Neuraxis registry."""
    data = _minimal()
    data["enforcement"]["on_missing_attestation"] = "allow"
    with pytest.raises(RegistryError, match="fail-closed"):
        load_registry(_write(tmp_path, data))


def test_empty_band_is_rejected(tmp_path):
    data = _minimal()
    data["bands"]["BAND-EMPTY"] = {"requires": ["GV-01"], "depends_on": []}
    with pytest.raises(RegistryError, match="no capabilities"):
        load_registry(_write(tmp_path, data))


def test_role_granted_undefined_band_is_rejected(tmp_path):
    data = _minimal()
    data["authority"]["role_grants"]["ghost"] = ["BAND-Q"]
    with pytest.raises(RegistryError, match="undefined band"):
        load_registry(_write(tmp_path, data))


@pytest.mark.parametrize(
    "text,expected",
    [("30s", timedelta(seconds=30)), ("15m", timedelta(minutes=15)),
     ("24h", timedelta(hours=24)), ("7d", timedelta(days=7))],
)
def test_parse_duration_accepts_valid_forms(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "24", "h", "-1h", "0h", "1 hour", "1w"])
def test_parse_duration_rejects_everything_else(text):
    with pytest.raises(RegistryError):
        parse_duration(text)
