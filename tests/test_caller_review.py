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
    """The worst finding of the fourth review: a caller that never executed a
    gate scored 12/12 by reading `spec.json` and forging `invocations.jsonl`.

    Pinned by the property rather than by the absence of one filename: the
    caller below searches every path it is handed for anything that would tell
    it the answer. If a future harness leaks the verdict again, this fails. The
    version this replaces asserted only that `spec.json` was gone, and passed
    for a caller that touched nothing at all.
    """
    report = check_caller(_caller(tmp_path, "oracle_files", """
        import json, os, pathlib, sys
        sys.stdin.read()
        roots = []
        for var in ("NEURAXIS_BIN", "NEURAXIS_BIN_ARGS"):
            raw = os.environ.get(var, "")
            for cand in (json.loads(raw) if raw.startswith("[") else [raw]):
                try:
                    roots.append(pathlib.Path(str(cand)).parent)
                except Exception:
                    pass
        for root in roots:
            try:
                names = [q.name for q in root.iterdir()]
            except Exception:
                continue
            for name in names:
                try:
                    text = (root / name).read_text()
                except Exception:
                    continue
                if '"exit_code"' in text or '"decision"' in text:
                    sys.exit(0 if '"exit_code": 0' in text else 1)
        sys.exit(1)
    """))
    assert "allow" in _failed(report), "something in the harness still leaks the verdict"
    assert "called" in _failed(report)


def test_the_scenario_name_is_not_in_the_callers_environment(tmp_path):
    """Exactly one scenario expects the caller to issue.

    So an environment variable naming the scenario is a complete answer key:
    `exit(0 if $NEURAXIS_CONFORMANCE_SCENARIO == "allow" else 1)` passed every
    exit-code check, while the same caller issued unconditionally in
    production, where the variable is unset. It was defended in a comment as
    unpreventable fingerprinting. Fingerprinting is unpreventable; handing over
    the answer is not the same thing, and it had no consumer.
    """
    report = check_caller(_caller(tmp_path, "oracle_env", """
        import json, os, subprocess, sys
        req = json.loads(sys.stdin.read())
        b = os.environ.get("NEURAXIS_BIN")
        args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
        if b:
            try:
                subprocess.run([b, *args, "--json", "gate", "-"],
                               input=json.dumps(req), capture_output=True,
                               text=True, timeout=15)
            except Exception:
                pass
        name = os.environ.get("NEURAXIS_CONFORMANCE_SCENARIO")
        if name is None:
            sys.exit(0)                    # production: issue every lease
        sys.exit(0 if name == "allow" else 1)
    """))
    assert not report.conforms
    assert "deny" in _failed(report)


def test_the_request_is_minted_per_run_not_a_constant():
    """`REFERENCE_REQUEST` is a module constant, so stdin identified the harness."""
    from neuraxis.caller import _mint_request

    seen = {_mint_request()["identity"] for _ in range(3)}
    assert len(seen) == 3, "the minted request repeats"
    minted = _mint_request()
    assert minted["verifier"] == minted["identity"], "W9's property must survive minting"
    assert minted["scope"] == REFERENCE_REQUEST["scope"], "the structural fields must not move"


def test_reaching_the_gate_without_executing_it_is_reported(tmp_path):
    """`called` counted TCP connections, not gate executions.

    The port is in NEURAXIS_BIN_ARGS, so a caller could open the socket itself
    and manufacture a perfect record while never running the configured binary.
    The record now carries the gate's own argv, which a caller taking that
    shortcut does not have.

    What this does NOT prove is that a caller which also forges the argv ran the
    binary. That needs the peer's process identity, and `called`'s rule text now
    says so rather than claiming otherwise.
    """
    report = check_caller(_caller(tmp_path, "wire", """
        import json, os, socket, sys
        req = json.loads(sys.stdin.read())
        args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
        if len(args) < 2:
            sys.exit(1)
        s = socket.create_connection(("127.0.0.1", int(args[1])), timeout=10)
        s.sendall(json.dumps({"stdin": json.dumps(req, sort_keys=True), "argv": []}).encode())
        s.shutdown(socket.SHUT_WR)
        buf = b""
        while True:
            c = s.recv(65536)
            if not c:
                break
            buf += c
        s.close()
        r = json.loads(buf.decode())
        ok = r["exit_code"] == 0 and json.loads(r["stdout"] or "{}").get("decision") == "ALLOW"
        sys.exit(0 if ok else 1)
    """))
    assert "fidelity" in _failed(report)
    detail = next(c.detail for c in report.checks if c.scenario == "fidelity")
    assert "nothing shows NEURAXIS_BIN was executed" in detail


def test_a_caller_that_reads_only_the_verdict_is_caught(tmp_path):
    """The mirror of the module's headline failure, and it was missing.

    Every scenario paired exit 0 with a DENY verdict, or a non-zero exit with no
    verdict. Nothing paired a NON-ZERO exit with an ALLOW verdict, so a caller
    that never read the exit code at all conformed - and in production issues on
    any gate that printed a verdict and then died.
    """
    report = check_caller(_caller(tmp_path, "verdict_only", """
        import json, os, subprocess, sys
        req = json.loads(sys.stdin.read())
        b = os.environ.get("NEURAXIS_BIN")
        args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
        if not b:
            sys.exit(1)
        try:
            p = subprocess.run([b, *args, "--json", "gate", "-"], input=json.dumps(req),
                               capture_output=True, text=True, timeout=15)
        except Exception:
            sys.exit(1)
        try:
            ok = json.loads(p.stdout).get("decision") == "ALLOW"
        except Exception:
            ok = False
        sys.exit(0 if ok else 1)
    """))
    assert "allow_verdict_nonzero_exit" in _failed(report)


def test_a_stamped_timestamp_is_validated_rather_than_waived(tmp_path):
    """`requested_at` was subtracted from the added set and never value-checked,
    making it the one field a caller could inject with any content at all - a
    timestamp chosen to sit inside a change freeze, or outside a replay window.
    """
    report = check_caller(_caller(tmp_path, "stamp", _ASK + """
    req["requested_at"] = "2099-01-01T00:00:00+00:00"
    sys.exit(0 if ask(req) else 1)
    """))
    assert "fidelity" in _failed(report)
    detail = next(c.detail for c in report.checks if c.scenario == "fidelity")
    assert "requested_at" in detail


def test_an_honest_stamp_is_accepted(tmp_path):
    """The positive control for the rule above: stamping is legitimate."""
    report = check_caller(_caller(tmp_path, "honest_stamp", _ASK + """
    from datetime import datetime, timezone
    req["requested_at"] = datetime.now(timezone.utc).isoformat()
    v = ask(req)
    if v is None:
        sys.exit(1)
    sys.exit(0 if v else 1)
    """))
    assert "fidelity" not in _failed(report), [c.detail for c in report.failures]


def test_extra_flags_on_the_gates_command_line_are_caught(tmp_path):
    """The argv was recorded and never compared. For a CLI gate the arguments
    carry as much authority as the body: a subcommand, a `--force`, a registry
    override pointing somewhere permissive.
    """
    report = check_caller(_caller(tmp_path, "forceflag", """
        import json, os, subprocess, sys
        req = json.loads(sys.stdin.read())
        b = os.environ.get("NEURAXIS_BIN")
        args = json.loads(os.environ.get("NEURAXIS_BIN_ARGS") or "[]")
        if not b:
            sys.exit(1)
        try:
            p = subprocess.run([b, *args, "--json", "gate", "-", "--force", "--skip-gate"],
                               input=json.dumps(req), capture_output=True, text=True, timeout=15)
        except Exception:
            sys.exit(1)
        if p.returncode != 0:
            sys.exit(1)
        try:
            sys.exit(0 if json.loads(p.stdout).get("decision") == "ALLOW" else 1)
        except Exception:
            sys.exit(1)
    """))
    assert "fidelity" in _failed(report)
    detail = next(c.detail for c in report.checks if c.scenario == "fidelity")
    assert "--force" in detail


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


def test_fidelity_compares_exactly_and_the_test_fails_if_that_is_reverted():
    """This test used to pass with its own fix reverted.

    It drove a caller that upper-cased the identity and asserted `fidelity`
    failed - which it did, but through a branch that rejects `AGENT-MOTOR`
    anyway. Nothing exercised a case where the folded and unfolded comparisons
    DIFFER, which is the only case a fold is for. A regression test that passes
    with the regression in place is the vacuous probe, in the suite written to
    catch vacuous probes.

    Chasing that turned up something worse: the fold applied to principals was
    not safer. Two names both carrying invisible codepoints both fold to `""`
    and compare EQUAL, which plain comparison catches. The fidelity question is
    not "do these two names denote the same principal" but "are these the bytes
    the caller was handed", so it now compares exactly - and this pins each way
    a fold or a strip would let something through.
    """
    from neuraxis.caller import _compare, _mint_request

    base = dict(_mint_request())

    def mangled(**changes):
        sent = dict(base)
        sent.update(changes)
        return _compare(sent, base)

    assert _compare(dict(base), base) == [], "the control failed"

    # A strip would excuse this; it is what lands in the evidence record.
    assert mangled(scope=f"  {base['scope']}  "), "padded scope compared equal"
    # A casefold would excuse this.
    assert mangled(identity=base["identity"].upper()), "case-mangled identity compared equal"
    # A fold that maps invisibles to "" would excuse this pair, because BOTH sides
    # collapse to the same empty string.
    both_invisible = _compare(
        {**base, "identity": base["identity"] + "\u200b"},
        {**base, "identity": base["identity"] + "\u200c"},
    )
    assert both_invisible, "two different invisible-bearing names compared equal"


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
