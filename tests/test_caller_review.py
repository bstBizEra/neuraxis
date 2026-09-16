"""The fourth adversarial review, on the caller and source suites (v0.17.0).

Three reviews had been run on the gate. The suites that certify *other people's*
code -- the assurance account's probe, L0's lease issuer, BADF's export -- had
never had one, and four releases had shipped since the last pass.

Every test here is an exploit that scored `conforms: True` against the shipped
code, reproduced by execution before it was fixed. They are kept as tests for
the reason `examples/vacuous_source.py` is kept in the repository: a suite
nobody has seen fail is itself an unverified check.

The shape of what was found: **everything the suite treated as evidence was
writable by the thing being measured.** Nine of the twelve checks read the
caller's exit code. The other three read a log file in a directory the harness
had named to the caller, written by a stub that ignored its input.
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from neuraxis.caller import REFERENCE_REQUEST, check_caller
from neuraxis.conformance import SCENARIOS, check_source, scenarios_for


def _caller(tmp_path, name: str, body: str) -> list[str]:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return [sys.executable, str(path)]


def _source(tmp_path, name: str, body: str) -> list[str]:
    return _caller(tmp_path, name, body)


def _failed(report) -> set[str]:
    return {c.scenario for c in report.failures}


_ASK = """
    import json, os, subprocess, sys
    req = json.loads(sys.stdin.read())
    binary = os.environ.get("NEURAXIS_BIN", "neuraxis")
    args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
    def ask(r):
        try:
            p = subprocess.run([binary, *args, "--json", "gate", "-"],
                               input=json.dumps(r), capture_output=True,
                               text=True, timeout=15)
        except Exception:
            return None
        if p.returncode != 0:
            return False
        try:
            return json.loads(p.stdout).get("decision") == "ALLOW"
        except Exception:
            return False
"""


# ---- the harness no longer hands the caller its own answer key ----------


def test_a_caller_cannot_read_the_verdict_without_asking_for_it(tmp_path):
    """The worst finding: a caller that never executed a gate scored 12/12.

    The harness wrote the scenario's answer to `spec.json` and the invocation
    log to `invocations.jsonl`, both in a directory whose absolute path it put
    into NEURAXIS_BIN_ARGS. The caller read the answer, appended a forged
    record, and `called` reported nine invocations.
    """
    report = check_caller(_caller(tmp_path, "oracle", """
        import json, os, pathlib, sys
        handed = sys.stdin.read()
        args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
        root = pathlib.Path(args[0]).parent if args else pathlib.Path(".")
        spec = root / "spec.json"
        if not spec.exists():
            sys.exit(1)
        answer = json.loads(spec.read_text())
        with (root / "invocations.jsonl").open("a") as fh:
            fh.write(json.dumps({"argv": [], "stdin": handed}) + "\\n")
        sys.exit(0 if answer.get("exit_code") == 0 else 1)
    """))
    assert not report.conforms
    failed = _failed(report)
    assert "called" in failed, "the forged log was believed"
    assert "allow" in failed, "the answer key was still readable"


def test_the_invocation_log_is_not_writable_by_the_caller(tmp_path):
    """A caller that writes plausible records everywhere cannot manufacture a
    `called` pass, because the record lives in the harness."""
    report = check_caller(_caller(tmp_path, "forger", """
        import json, os, pathlib, sys
        sys.stdin.read()
        for var in ("NEURAXIS_BIN", "NEURAXIS_BIN_ARGS"):
            raw = os.environ.get(var, "")
            for candidate in (json.loads(raw) if raw.startswith("[") else [raw]):
                try:
                    d = pathlib.Path(candidate).parent
                    (d / "invocations.jsonl").write_text(
                        json.dumps({"argv": [], "stdin": "{}"}) + "\\n")
                except Exception:
                    pass
        sys.exit(1)
    """))
    assert "called" in _failed(report)


# ---- fidelity: added, altered, on every call, in every scenario ---------


def test_an_added_ratification_reference_is_caught(tmp_path):
    """`fidelity` used to walk the expected fields asking "was anything lost".

    The dangerous direction is the other one. `ratification_ref` is a known
    optional field, so it survives `from_dict`, and any non-blank string clears
    the non-delegable floor and the GV-07 requirement. Every field the caller
    was handed did arrive unchanged.
    """
    report = check_caller(_caller(tmp_path, "injector", _ASK + """
    req["ratification_ref"] = "PR-000"
    v = ask(req)
    sys.exit(0 if v else 1)
    """))
    assert "fidelity" in _failed(report)
    detail = next(c.detail for c in report.checks if c.scenario == "fidelity")
    assert "ratification_ref" in detail
    assert "non-delegable floor" in detail


@pytest.mark.parametrize("field", ["performer", "envelope_ref", "adjustments"])
def test_any_added_optional_field_is_caught(tmp_path, field):
    value = {"retries": 5} if field == "adjustments" else "injected"
    report = check_caller(_caller(tmp_path, f"inject_{field}", _ASK + f"""
    req[{field!r}] = {value!r}
    sys.exit(0 if ask(req) else 1)
    """))
    assert "fidelity" in _failed(report)


def test_doctoring_the_request_and_retrying_is_caught(tmp_path):
    """The caller a real team writes under schedule pressure.

    Ask faithfully. Get a DENY. Conclude the verifier field is confusing it.
    Retry without it and honour that answer. Every earlier version of this
    suite reported `conforms: True`, because the scripted gate's reply never
    varied with the request and `fidelity` looked only at the last call of the
    `allow` scenario.
    """
    report = check_caller(_caller(tmp_path, "retrier", _ASK + """
    first = ask(req)
    if first is None:
        sys.exit(1)
    if first:
        sys.exit(0)
    retry = dict(req)
    retry.pop("verifier", None)
    retry["risk"] = "LOW"
    sys.exit(0 if ask(retry) else 1)
    """))
    failed = _failed(report)
    assert "fidelity_trap" in failed, "the trap scenario did not catch the retry"
    assert "fidelity" in failed


def test_a_doctored_first_call_with_a_faithful_decoy_is_caught(tmp_path):
    """`fidelity` read `invocations[-1]`, so a faithful second call hid the first."""
    report = check_caller(_caller(tmp_path, "decoy", _ASK + """
    sneaky = dict(req)
    sneaky.pop("verifier", None)
    sneaky["scope"] = "bst-sa"
    decision = ask(sneaky)
    ask(req)                     # decoy, answer discarded
    sys.exit(0 if decision else 1)
    """))
    assert "fidelity" in _failed(report)


def test_fidelity_covers_the_blocking_scenarios_not_only_allow(tmp_path):
    """Doctoring only when the gate says no was invisible: fidelity ran on
    `allow` alone, and `allow` is the one scenario a caller has no reason to
    doctor."""
    report = check_caller(_caller(tmp_path, "onblock", _ASK + """
    v = ask(req)
    if v:
        sys.exit(0)
    bad = dict(req)
    bad["identity"] = "someone-else"
    ask(bad)
    sys.exit(1)
    """))
    detail = next(c.detail for c in report.checks if c.scenario == "fidelity")
    assert "fidelity" in _failed(report)
    assert "deny call" in detail or "escalate call" in detail


def test_a_principal_compares_strictly_because_equality_certifies(tmp_path):
    """`.casefold()` accepted `AGENT-MOTOR` as the principal the gate reasons about.

    Equality here certifies the caller as faithful, so by this package's own
    rule it takes `strict_principal`, not a fold that collapses distinct names.
    """
    report = check_caller(_caller(tmp_path, "mangler", _ASK + """
    req["identity"] = req["identity"].upper()
    sys.exit(0 if ask(req) else 1)
    """))
    assert "fidelity" in _failed(report)


def test_a_boolean_sent_as_a_number_is_caught(tmp_path):
    """`1 == True` in Python, so the value comparison alone would accept it."""
    report = check_caller(_caller(tmp_path, "numeric", _ASK + """
    req["rollback_tested"] = 1
    sys.exit(0 if ask(req) else 1)
    """))
    assert "fidelity" in _failed(report)


# ---- the production default -------------------------------------------


def test_an_unconfigured_gate_is_not_an_absent_objection(tmp_path):
    """Every scenario used to SET NEXURAXIS_BIN, including `missing`, which
    pointed it at a path that did not exist. The state where nobody has
    configured the gate yet -- the default of any fresh deployment -- was the
    one branch the suite could not reach."""
    report = check_caller(_caller(tmp_path, "unconfigured", """
        import json, os, subprocess, sys
        sys.stdin.read()
        binary = os.environ.get("NEURAXIS_BIN")
        if not binary:
            sys.exit(0)       # "not configured yet" -> issue
        sys.exit(1)
    """))
    assert "unconfigured" in _failed(report)


def test_the_reference_callers_still_conform():
    """The positive control for the whole review: the fixes did not simply
    tighten everything into rejecting honest callers."""
    for path in ("examples/conforming_caller.py", "clients/js/examples/issue_lease.mjs"):
        runner = [sys.executable, path] if path.endswith(".py") else ["node", path]
        report = check_caller(runner)
        assert report.conforms, (path, [c.detail for c in report.failures])


def test_the_credulous_caller_now_also_fails_the_trap():
    report = check_caller([sys.executable, "examples/credulous_caller.py"])
    failed = _failed(report)
    assert {"fidelity", "fidelity_trap"} <= failed
    assert "deny" not in failed, "it does block on DENY - that is what makes it plausible"


# ---- the source suite had the same two holes ---------------------------


def test_a_source_hardcoded_to_fail_no_longer_conforms(tmp_path):
    """Rule 2 was labelled "positive control" and only proved a source could
    emit FAIL. A source hardcoded to `{"result": false}` satisfied every rule."""
    report = check_source(_source(tmp_path, "alwaysfail", """
        import json, sys
        from datetime import datetime, timezone
        req = json.load(sys.stdin)
        json.dump({"control": req["control"], "result": False,
                   "issued_at": datetime.now(timezone.utc).isoformat(),
                   "issuer": "x", "evidence_ref": "test://ref/1"}, sys.stdout)
    """), "GV-01")
    assert not report.conforms
    assert "positive" in {r.scenario for r in report.failures}


def test_a_source_that_declines_the_vacuity_scenario_no_longer_conforms(tmp_path):
    """It used to pass, and the report said it "distinguishes a powerless
    identity from a powerful one". It distinguished nothing; it crashed."""
    report = check_source(_source(tmp_path, "nopowerless", """
        import json, sys
        from datetime import datetime, timezone
        req = json.load(sys.stdin)
        s = req["scenario"]
        if s == "powerless":
            sys.stderr.write("KeyError\\n")
            sys.exit(1)
        json.dump({"control": req["control"], "result": s in ("live", "positive"),
                   "issued_at": datetime.now(timezone.utc).isoformat(),
                   "issuer": "x", "evidence_ref": "test://ref/1"}, sys.stdout)
    """), "GV-01")
    assert not report.conforms
    failure = next(r for r in report.failures if r.scenario == "powerless")
    assert "demonstrated no distinction" in failure.detail


def test_a_source_that_hangs_on_a_scenario_no_longer_conforms(tmp_path):
    """A hanging source produced `result is None`, which satisfied both the
    fail-closed rule and the vacuity rule."""
    report = check_source(_source(tmp_path, "hang", """
        import json, sys, time
        from datetime import datetime, timezone
        req = json.load(sys.stdin)
        s = req["scenario"]
        if s in ("broken", "powerless"):
            time.sleep(30)
        json.dump({"control": req["control"], "result": s in ("live", "positive"),
                   "issued_at": datetime.now(timezone.utc).isoformat(),
                   "issuer": "x", "evidence_ref": "test://ref/1"}, sys.stdout)
    """), "GV-01", timeout=1.0)
    assert not report.conforms


def test_both_halves_of_the_demonstration_are_required():
    assert "positive" in SCENARIOS and "negative" in SCENARIOS
    # An audit legitimately answers the same whoever asks, so it skips vacuity  - 
    # but it still has to show it can say both words.
    assert "powerless" not in scenarios_for("audit")
    assert {"positive", "negative"} <= set(scenarios_for("audit"))


# ---- what the reference request is for ---------------------------------


def test_the_reference_request_still_names_its_performer_as_its_verifier():
    assert REFERENCE_REQUEST["verifier"] == REFERENCE_REQUEST["identity"]
