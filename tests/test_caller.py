"""The gate-caller conformance suite (ILR-001-DR D-07).

D-07 chose the cheapest integration -- L0 shells out to `neuraxis gate` -- and
in doing so moved the entire enforcement burden to the other side of a process
boundary. These tests are about the ways a caller can look correct and license
everything, and about the ways this suite could report conformance for a caller
that never demonstrated anything.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import textwrap

import pytest

from neuraxis import (
    BLOCKING_EVENTS,
    CALLER_SCENARIOS,
    AuthorityRequest,
    ConformanceError,
    Decision,
    check_caller,
)
from neuraxis.caller import REFERENCE_REQUEST
from neuraxis.cli import EXIT_BY_DECISION, EXIT_ERROR, main

EXAMPLES = "examples"
_CONTRACT_DOC = pathlib.Path("docs/L0-LEASE-GATE-CONTRACT.md")


def _example(name: str) -> list[str]:
    return [sys.executable, f"{EXAMPLES}/{name}.py"]


def _caller(tmp_path, name: str, body: str) -> list[str]:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(path)]


#: A faithful caller, in as few lines as the contract allows. Tests below vary
#: one thing about it at a time.
_FAITHFUL = """
    import json, os, subprocess, sys
    req = json.loads(sys.stdin.read())
    argv = [os.environ.get("NEURAXIS_BIN", "neuraxis")]
    argv += json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
    argv += ["--json", "gate", "-"]
    try:
        r = subprocess.run(argv, input=json.dumps(req), capture_output=True,
                           text=True, timeout=15, check=False)
    except Exception:
        sys.exit(1)
    if r.returncode != 0:
        sys.exit(1)
    try:
        v = json.loads(r.stdout)
    except ValueError:
        sys.exit(1)
    if v.get("decision") != "ALLOW":
        sys.exit(1)
    sys.exit(0)
"""


def _by_scenario(report):
    return {c.scenario: c for c in report.checks}


# ---- the reference implementations ------------------------------------


def test_the_reference_caller_conforms():
    report = check_caller(_example("conforming_caller"))
    assert report.conforms, [c.detail for c in report.failures]


def test_the_credulous_caller_fails_exactly_where_the_docstring_says():
    report = check_caller(_example("credulous_caller"))
    failures = {c.scenario for c in report.failures}
    # Blocking on exit 10 licenses the other three blocking decisions and the
    # CLI fault; dropping `verifier` switches off W9.
    assert {
        "escalate", "wait_for_authority", "delegate", "fault", "fidelity"
    } <= failures
    assert "deny" not in failures, "it does block on DENY -- that is what makes it plausible"


# ---- the scenario set is not allowed to go stale -----------------------


def test_every_decision_has_a_scenario():
    """Adding a Decision must break this, not widen a caller's authority.

    A decision with no scenario is an exit code no caller was ever tested
    against, and an untested exit code in a governance client is one somebody
    maps to nothing -- which in a gate means 'not recognised as a block'.
    """
    assert {d.value.lower() for d in Decision} <= set(CALLER_SCENARIOS)


def test_the_blocking_events_are_all_five_of_D_03s():
    assert set(BLOCKING_EVENTS) == {
        "lease_issue", "lease_widen", "band_transition", "envelope_amend", "verifier_assign"
    }


def test_the_contract_publishes_the_caller_half(capsys):
    assert main(["--json", "contract"]) == 0
    payload = json.loads(capsys.readouterr().out)
    caller = payload["caller"]
    assert caller["proceed_only_on_exit"] == 0
    assert caller["blocking_events"] == list(BLOCKING_EVENTS)
    assert caller["conformance_scenarios"] == list(CALLER_SCENARIOS)
    assert caller["bin_env"] == "NEURAXIS_BIN"


# ---- the reference request is the request W9 turns on ------------------


def test_the_reference_request_is_one_the_gate_would_parse():
    """If the harness sent a malformed request every caller would fail `fault`
    for the wrong reason, and the suite would be measuring its own bug."""
    AuthorityRequest.from_dict(dict(REFERENCE_REQUEST))


def test_the_reference_request_names_its_performer_as_its_verifier():
    """The fidelity check is only load-bearing because of this.

    A caller that drops `verifier` turns this exact request from a DENY into an
    ALLOW, with nothing in between reporting an error.
    """
    assert REFERENCE_REQUEST["verifier"] == REFERENCE_REQUEST["identity"]


# ---- the ways a caller fails -------------------------------------------


def test_a_caller_that_refuses_everything_fails_the_positive_control(tmp_path):
    report = check_caller(_caller(tmp_path, "paranoid", "import sys; sys.exit(1)"))
    assert not report.conforms
    failures = {c.scenario for c in report.failures}
    assert "allow" in failures
    assert "called" in failures


def test_a_caller_that_issues_without_asking_fails_called(tmp_path):
    report = check_caller(_caller(tmp_path, "cached", "import sys; sys.exit(0)"))
    checks = _by_scenario(report)
    assert not checks["called"].ok
    assert checks["called"].invocations == 0
    assert "without invoking the gate" in checks["called"].detail


def test_blocking_on_ten_alone_licenses_the_other_blocking_decisions(tmp_path):
    """The README's standing warning, as a failing scenario rather than a sentence.

    The exit test is the only thing changed. Every other line of the faithful
    caller is intact, which is what makes this the realistic bug: it blocks on
    DENY, it looks like it works, and it grants authority on the three other
    decisions that also mean no.
    """
    body = (
        _FAITHFUL
        .replace("if r.returncode != 0:", "if r.returncode == 10:")
        .replace('if v.get("decision") != "ALLOW":\n        sys.exit(1)', "")
    )
    report = check_caller(_caller(tmp_path, "tenonly", body))
    failures = {c.scenario for c in report.failures}
    assert {"escalate", "wait_for_authority", "delegate"} <= failures
    assert "deny" not in failures


def test_checking_the_decision_field_covers_for_a_wrong_exit_test(tmp_path):
    """Two independent reads of one answer, and the second one saves the first.

    A caller that tests `== 10` but also insists the verdict says ALLOW still
    refuses an ESCALATE -- the verdict field catches what the exit code missed.
    Worth pinning: it is the reason a caller can pass this suite with a latent
    exit-code bug, and the reason the reference implementation keeps both
    checks rather than picking the one that looks sufficient.
    """
    body = _FAITHFUL.replace("if r.returncode != 0:", "if r.returncode == 10:")
    report = check_caller(_caller(tmp_path, "belt_and_braces", body))
    assert report.conforms, [c.detail for c in report.failures]


def test_a_dropped_field_is_caught_even_though_nothing_errors(tmp_path):
    body = _FAITHFUL.replace(
        "input=json.dumps(req)",
        'input=json.dumps({k: v for k, v in req.items() if k != "verifier"})',
    )
    report = check_caller(_caller(tmp_path, "dropper", body))
    checks = _by_scenario(report)
    assert checks["allow"].ok, "the gate was scripted to ALLOW, so nothing surfaces the drop"
    assert not checks["fidelity"].ok
    assert "verifier" in checks["fidelity"].detail


def test_a_rewritten_scope_is_caught(tmp_path):
    body = _FAITHFUL.replace(
        "input=json.dumps(req)",
        'input=json.dumps({**req, "scope": "bst-sa"})',
    )
    report = check_caller(_caller(tmp_path, "widener", body))
    checks = _by_scenario(report)
    assert not checks["fidelity"].ok
    assert "scope" in checks["fidelity"].detail


def test_a_caller_that_hangs_has_not_refused(tmp_path):
    report = check_caller(
        _caller(tmp_path, "hang", "import time; time.sleep(30)"), timeout=1.0
    )
    checks = _by_scenario(report)
    assert not checks["allow"].ok
    assert checks["allow"].observed == "no answer"
    assert "has not refused" in checks["allow"].detail


def test_a_caller_that_sends_the_gate_nothing_fails_fidelity(tmp_path):
    body = _FAITHFUL.replace("input=json.dumps(req)", 'input=""')
    report = check_caller(_caller(tmp_path, "empty", body))
    checks = _by_scenario(report)
    assert not checks["fidelity"].ok


# ---- the suite refuses to guess ----------------------------------------


def test_a_command_line_string_is_refused_not_split():
    with pytest.raises(ConformanceError) as exc:
        check_caller("python C:\\l0\\issue_lease.py")
    assert "backslashes" in str(exc.value)


def test_an_empty_command_is_refused():
    with pytest.raises(ConformanceError):
        check_caller([])


def test_a_caller_that_does_not_exist_is_an_error_not_a_verdict(tmp_path):
    with pytest.raises(ConformanceError) as exc:
        check_caller([str(tmp_path / "no-such-caller")])
    assert "caller not found" in str(exc.value)


# ---- the CLI ------------------------------------------------------------


def test_cli_exits_zero_for_a_conforming_caller(capsys):
    assert main(["caller-conform", "--", *_example("conforming_caller")]) == 0
    out = capsys.readouterr().out
    assert "conforms at the entry point it was given" in out
    # The headline claim is scoped in the output itself, not only in the docs.
    assert "each needs its own conforming entry point" in out


def test_cli_exits_ten_for_a_caller_that_does_not(capsys):
    assert main(["caller-conform", "--", *_example("credulous_caller")]) == 10
    assert "Do not route authority grants through it" in capsys.readouterr().out


def test_cli_json_carries_every_check(capsys):
    assert main(["--json", "caller-conform", "--", *_example("conforming_caller")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conforms"] is True
    scenarios = [c["scenario"] for c in payload["checks"]]
    assert scenarios == [*CALLER_SCENARIOS, "called", "fidelity"]


# ---- the published document is not allowed to go stale -----------------


def test_the_contract_doc_publishes_the_exit_codes_the_cli_uses():
    """A stale exit-code table in the integration contract is the exact failure
    the contract warns L0 about. It should not be in the contract itself."""
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    for decision, code in EXIT_BY_DECISION.items():
        assert re.search(rf"^exit {code}\s+{decision.value}\b", text, re.M), (
            f"{decision.value} is exit {code} in the CLI and not in the document"
        )
    assert re.search(rf"^exit {EXIT_ERROR}\s", text, re.M)


def test_the_contract_doc_names_every_blocking_event():
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    for event in BLOCKING_EVENTS:
        assert event in text, f"{event} is a call site the document never mentions"


def test_the_contract_doc_names_every_conformance_scenario():
    text = _CONTRACT_DOC.read_text(encoding="utf-8")
    for scenario in (*CALLER_SCENARIOS, "called", "fidelity"):
        assert f"`{scenario}`" in text, f"{scenario} is a check the document never mentions"
