"""The attestation source conformance suite (v0.11.0).

The controls that matter most will be attested by sources written outside this
repository. These tests are mostly about the ways such a source can look fine
and check nothing -- and about the ways this suite could report conformance for
a source that never demonstrated anything.
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest
import yaml

from neuraxis import ConformanceError, check_source, load_registry, scenarios_for
from neuraxis.cli import main
from neuraxis.conformance import SCENARIOS
from neuraxis.errors import RegistryError

EXAMPLES = "examples"


def _source(name: str) -> list[str]:
    return [sys.executable, f"{EXAMPLES}/{name}.py"]


def _script(tmp_path, name: str, body: str) -> list[str]:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(path)]


_EMIT = """
    import json, sys
    from datetime import datetime, timezone
    req = json.load(sys.stdin)
    out = dict(BODY)
    out.setdefault("control", req.get("control"))
    out.setdefault("issued_at", datetime.now(timezone.utc).isoformat())
    out.setdefault("issuer", "test/source")
    out.setdefault("evidence_ref", "test://ref/1")
    json.dump(out, sys.stdout)
"""


def _emitter(tmp_path, name: str, body: str) -> list[str]:
    return _script(tmp_path, name, _EMIT.replace("BODY", body))


# ---- which scenarios apply --------------------------------------------


def test_a_probe_must_answer_the_vacuity_scenario():
    assert scenarios_for("probe") == SCENARIOS
    assert "powerless" in scenarios_for("probe")


def test_an_audit_is_not_asked_the_vacuity_scenario():
    """An audit of a log legitimately answers the same whoever asks."""
    assert scenarios_for("audit") == ("live", "broken", "negative")


@pytest.mark.parametrize("kind", ["", "PROBE ", "drill", "nonsense", "Audit "])
def test_an_unrecognised_kind_is_treated_as_a_probe(kind):
    """An unknown kind must not be a way out of a check."""
    expected = ("live", "broken", "negative") if kind.strip().lower() == "audit" else SCENARIOS
    assert scenarios_for(kind) == expected


# ---- the reference sources --------------------------------------------


def test_the_reference_source_conforms():
    """The positive control for the suite itself."""
    report = check_source(_source("conforming_source"), "GV-01", kind="probe")
    assert report.conforms, [r.detail for r in report.failures]
    assert len(report.results) == 4


def test_the_vacuous_source_is_caught_on_three_rules():
    """A suite nobody has seen fail is itself an unverified check."""
    report = check_source(_source("vacuous_source"), "GV-01", kind="probe")
    assert not report.conforms
    assert {r.scenario for r in report.failures} == {"broken", "negative", "powerless"}
    # It still passes rule 4: it emits a plausible reference. That is the point
    # of keeping it -- a source can satisfy the visible rule and none of the
    # substantive ones.
    assert next(r for r in report.results if r.scenario == "live").ok


def test_the_vacuous_source_passes_when_only_audited_on_three_rules_is_still_false():
    """Declaring `audit` drops the vacuity check but not the other two."""
    report = check_source(_source("vacuous_source"), "GV-02", kind="audit")
    assert not report.conforms
    assert {r.scenario for r in report.failures} == {"broken", "negative"}


# ---- rule 4: an evidence reference, not a verdict ----------------------


@pytest.mark.parametrize("ref", ["pass", "PASS", "ok", "true", "n/a", "-", "  "])
def test_a_verdict_is_not_an_evidence_reference(tmp_path, ref):
    src = _emitter(tmp_path, "v", f'{{"result": True, "evidence_ref": {ref!r}}}')
    report = check_source(src, "GV-01", kind="probe")
    live = next(r for r in report.results if r.scenario == "live")
    assert not live.ok
    assert "reference" in live.detail


def test_a_missing_evidence_reference_fails(tmp_path):
    src = _script(
        tmp_path, "noref",
        """
        import json, sys
        from datetime import datetime, timezone
        json.load(sys.stdin)
        json.dump({"control": "GV-01", "result": True,
                   "issued_at": datetime.now(timezone.utc).isoformat(),
                   "issuer": "t"}, sys.stdout)
        """,
    )
    live = next(r for r in check_source(src, "GV-01").results if r.scenario == "live")
    assert not live.ok and "evidence_ref" in live.detail


# ---- rule 1 and the shape of the attestation ---------------------------

def test_a_string_result_is_not_a_result(tmp_path):
    """`"false"` is a non-empty string and therefore truthy."""
    src = _emitter(tmp_path, "strres", '{"result": "false"}')
    live = next(r for r in check_source(src, "GV-01").results if r.scenario == "live")
    assert not live.ok
    assert "JSON boolean" in live.detail


def test_a_naive_timestamp_fails(tmp_path):
    src = _emitter(tmp_path, "naive", '{"result": True, "issued_at": "2026-09-16T09:00:00"}')
    live = next(r for r in check_source(src, "GV-01").results if r.scenario == "live")
    assert not live.ok and "timezone" in live.detail


def test_attesting_a_different_control_fails(tmp_path):
    src = _emitter(tmp_path, "wrong", '{"result": True, "control": "GV-09"}')
    live = next(r for r in check_source(src, "GV-01").results if r.scenario == "live")
    assert not live.ok and "not the control it was asked about" in live.detail


def test_a_source_that_writes_nothing_fails_live_but_conforms_on_rule_1(tmp_path):
    src = _script(tmp_path, "silent", "import sys; sys.stdin.read()")
    report = check_source(src, "GV-01", kind="probe")
    assert not report.conforms
    live = next(r for r in report.results if r.scenario == "live")
    broken = next(r for r in report.results if r.scenario == "broken")
    assert not live.ok and "wrote nothing" in live.detail
    # It did not report PASS, so rule 1 holds - but it is flagged, because
    # fail-closed by crashing depends on every caller converting it.
    assert broken.ok
    assert any("crashed or emitted nothing" in w for w in report.warnings)


def test_a_source_that_crashes_conforms_on_rule_1_with_a_warning(tmp_path):
    src = _script(tmp_path, "crash", "import sys; sys.stdin.read(); raise SystemExit(3)")
    report = check_source(src, "GV-01", kind="probe")
    broken = next(r for r in report.results if r.scenario == "broken")
    assert broken.ok and broken.exit_code == 3
    assert report.warnings


def test_a_hanging_source_is_not_a_pass(tmp_path):
    src = _script(tmp_path, "hang", "import sys, time; sys.stdin.read(); time.sleep(30)")
    report = check_source(src, "GV-01", kind="probe", timeout=1.0)
    assert not report.conforms
    broken = next(r for r in report.results if r.scenario == "broken")
    assert broken.result is None and broken.ok      # not a PASS
    live = next(r for r in report.results if r.scenario == "live")
    assert not live.ok


def test_non_json_output_fails_live(tmp_path):
    src = _script(tmp_path, "prose", "import sys; sys.stdin.read(); print('all good!')")
    live = next(r for r in check_source(src, "GV-01").results if r.scenario == "live")
    assert not live.ok and "not JSON" in live.detail


# ---- the harness's own footguns ---------------------------------------


def test_a_command_line_string_is_refused_rather_than_split():
    """shlex eats backslashes, so a Windows path would read as missing."""
    with pytest.raises(ConformanceError, match="list of arguments"):
        check_source(r"C:\python\python.exe probe.py", "GV-01")


def test_an_empty_command_is_refused():
    with pytest.raises(ConformanceError, match="no source command"):
        check_source([], "GV-01")


def test_a_blank_control_is_refused():
    with pytest.raises(ConformanceError, match="no control"):
        check_source([sys.executable, "-c", "pass"], "   ")


def test_a_missing_executable_is_an_error_not_a_verdict(tmp_path):
    with pytest.raises(ConformanceError, match="source not found"):
        check_source([str(tmp_path / "nope"), "x"], "GV-01")


# ---- the registry declares the kind -----------------------------------


def test_the_shipped_registry_declares_a_kind_for_every_control(registry):
    assert {c.kind for c in registry.controls.values()} <= {"probe", "audit"}
    assert registry.controls["GV-01"].kind == "probe"
    assert registry.controls["GV-07"].kind == "audit"


def _mini(kind_line):
    return {
        "framework": "test",
        "version": "0.1",
        "governance": {"GV-01": {"name": "identity", "attestation": "x/y", **kind_line}},
        "capabilities": {"IL-01": {"name": "Thinkable", "band": "BAND-A", "question": "?"}},
        "bands": {"BAND-A": {"requires": ["GV-01"], "depends_on": []}},
        "authority": {"role_grants": {"operator": ["BAND-A"]}},
        "enforcement": {"on_missing_attestation": "deny", "attestation_max_age": "24h"},
    }


def test_an_omitted_kind_defaults_to_the_stricter_one(tmp_path):
    """Omission must tighten. A default of `audit` would drop a check silently."""
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(_mini({})), encoding="utf-8")
    assert load_registry(path).controls["GV-01"].kind == "probe"


@pytest.mark.parametrize("bad", ["drill", "", True, 3, None, "PROBE?"])
def test_an_unrecognised_kind_is_refused_at_load(tmp_path, bad):
    path = tmp_path / "neuraxis.yaml"
    path.write_text(yaml.safe_dump(_mini({"kind": bad})), encoding="utf-8")
    with pytest.raises(RegistryError, match="'kind' must be one of"):
        load_registry(path)


# ---- CLI ---------------------------------------------------------------


def test_cli_conform_exits_zero_for_a_conforming_source(capsys):
    assert main(["conform", "--control", "GV-01", "--", *_source("conforming_source")]) == 0
    out = capsys.readouterr().out
    assert "this source conforms" in out
    assert "kind: probe, declared by the registry" in out


def test_cli_conform_exits_ten_for_a_vacuous_source(capsys):
    assert main(["conform", "--control", "GV-01", "--", *_source("vacuous_source")]) == 10
    out = capsys.readouterr().out
    assert "DOES NOT conform" in out
    assert "powerless" in out


def test_cli_conform_reads_the_kind_from_the_registry_not_the_source(capsys):
    """GV-07 is declared `audit`, so the same source is judged on three rules."""
    assert main(["conform", "--control", "GV-07", "--", *_source("vacuous_source")]) == 10
    payload_out = capsys.readouterr().out
    assert "kind: audit" in payload_out
    assert "powerless" not in payload_out.split("NOTE:")[0]


def test_cli_conform_json(capsys):
    assert main(["--json", "conform", "--control", "GV-01", "--", *_source("conforming_source")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conforms"] is True
    assert payload["kind"] == "probe"
    assert [s["scenario"] for s in payload["scenarios"]] == list(SCENARIOS)


def test_cli_conform_refuses_an_unknown_control(capsys):
    assert main(["conform", "--control", "GV-99", "--", sys.executable, "-c", "pass"]) == 2
    assert "unknown control" in capsys.readouterr().err


def test_cli_conform_reports_the_audit_kind_as_a_note(capsys):
    assert main(["conform", "--control", "GV-02", "--", *_source("conforming_source")]) == 0
    out = capsys.readouterr().out
    assert "NOTE:" in out and "check it is the right one there" in out
