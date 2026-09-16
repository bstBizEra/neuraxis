"""Conformance suite for gate callers (ILR-001-DR D-07).

`conformance.py` asks whether an attestation *source* can be trusted to attest
a control. This asks the mirror-image question about the other end of the
contract: whether a *caller* of `neuraxis gate` can be trusted to act on what
the gate tells it.

The question exists because of D-07. L0 does not embed the gate; it shells out
to the CLI at each of D-03's five blocking events and refuses the grant on any
non-zero exit. That choice costs nothing to build, which is why it was made --
and it moves the entire risk into the caller. Neuraxis can return DENY
perfectly and still license nothing, because the thing that issues the lease is
somewhere else, written by someone else, and nobody has ever tested that it
reads the answer correctly.

The failures this catches are the ones that look like working code:

  - blocking on exit 10 and treating 11 as success, which is the README's
    standing warning and the most likely way an ESCALATE becomes a grant;
  - treating a CLI fault (exit 2) as "the gate had no objection";
  - treating an exit code it has never seen as permission, so that adding a
    Decision on the Python side silently widens authority on the L0 side;
  - dropping `verifier` on the way to the gate, which does not fail anything
    and switches off W9 entirely;
  - issuing a lease without calling the gate at all.

**The contract.** The caller under test is an executable that issues one lease.

  in    one JSON object on stdin: the lease request, in `AuthorityRequest`
        field names.
  gate  it must invoke the gate resolved from `NEURAXIS_BIN` and, if set,
        `NEURAXIS_BIN_ARGS` (a JSON array of leading arguments) -- the same
        `{bin, binArgs}` split the Node client already exposes. A caller that
        hard-codes the path cannot be substituted with a scripted gate, and an
        untestable caller is an unproven one.
  out   exit 0 if it issued the lease, non-zero if it refused. Nothing else is
        read: what it printed is its own business.

The suite substitutes a scripted gate, drives the caller through the scenarios
below, and looks only at whether it issued or refused.

| scenario | the scripted gate returns | the caller must |
|---|---|---|
| `allow` | exit 0, an ALLOW verdict | issue |
| `deny` | exit 10, a DENY verdict | refuse |
| `escalate` | exit 11, an ESCALATE verdict | refuse |
| `wait_for_authority` | exit 12 | refuse |
| `delegate` | exit 13 | refuse |
| `fault` | exit 2, a message on stderr | refuse |
| `unknown_exit` | exit 47, no verdict | refuse |
| `contradiction` | exit 0, but the verdict says DENY | refuse |
| `silent` | exit 0, nothing on stdout | refuse |
| `missing` | the gate binary does not exist | refuse |

`allow` is the positive control. Without it a caller that refuses everything
scores nine out of nine, and a lease issuer that never issues is an outage
wearing a gate's clothes.

Two further checks are read from what reached the scripted gate rather than
from what the caller returned:

  - **called** -- the caller invoked the gate at least once in every scenario.
    A cached earlier ALLOW is the D-03 bypass, and it is invisible from the
    exit code alone.
  - **fidelity** -- the object that reached the gate parses as an
    `AuthorityRequest` and carries the same values it was handed. This is the
    one that catches a dropped `verifier`: the gate cannot enforce verifier
    independence over a field it was never sent, and nothing else in the chain
    notices.

**What this is not.** Every scenario is driven through the caller's own code
path, so passing shows the caller *refuses when the gate blocks* -- not that it
calls the gate at every place it should. The five blocking events in D-03 are
five call sites, and a suite driving one of them says nothing about the other
four. Each needs its own conforming entry point. The suite also does not test
timeout behaviour, because testing a hang means waiting on one; the contract
requires a hard timeout treated as refusal, and that requirement is unproven
here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .conformance import ConformanceError
from .model import REQUEST_REQUIRED_FIELDS, AuthorityRequest

__all__ = [
    "BLOCKING_EVENTS",
    "CALLER_SCENARIOS",
    "CallerCheck",
    "CallerReport",
    "REFERENCE_REQUEST",
    "check_caller",
]

DEFAULT_TIMEOUT = 30.0

#: ILR-001-DR D-03's synchronous-blocking events: every change to what a
#: component is *allowed* to do. Each is a separate call site in L0, and a
#: caller proven conforming at one of them says nothing about the other four --
#: which is why the list is published rather than left to be remembered.
BLOCKING_EVENTS: tuple[str, ...] = (
    "lease_issue",
    "lease_widen",
    "band_transition",
    "envelope_amend",
    "verifier_assign",
)

PROCEED = "issued"
REFUSE = "refused"
NO_ANSWER = "no answer"

#: The lease request handed to the caller on stdin. `verifier` is deliberately
#: the performing principal: under a faithful caller this is what W9 denies, so
#: a caller that drops the field turns a DENY into an ALLOW without any step in
#: between reporting an error.
REFERENCE_REQUEST: Mapping[str, Any] = {
    "intent": "issue a write lease over the pipeline definitions",
    "identity": "agent-motor",
    "role": "motor",
    "capability": "IL-06",
    "scope": "bst-sa/pipelines",
    "risk": "HIGH",
    "verifier": "agent-motor",
    "rollback_tested": True,
}

#: Fields whose value must survive the trip from the caller's stdin to the
#: gate's stdin unchanged.
_FIDELITY_FIELDS = tuple(REQUEST_REQUIRED_FIELDS) + ("risk", "verifier", "rollback_tested")

_ALLOW_VERDICT = {
    "decision": "ALLOW", "capability": "IL-06", "band": "BAND-B",
    "reasons": ["all required controls attested"], "obligations": [], "missing_controls": [],
    "verdict_id": "V-conformance-0001",
}
_DENY_VERDICT = {
    "decision": "DENY", "capability": "IL-06", "band": "BAND-B",
    "reasons": ["verifier 'agent-motor' is an identity this request claims"],
    "obligations": [], "missing_controls": [],
}


def _verdict(decision: str) -> str:
    payload = dict(_DENY_VERDICT)
    payload["decision"] = decision
    return json.dumps(payload, sort_keys=True)


@dataclass(frozen=True)
class _Scenario:
    name: str
    rule: str
    expect: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    #: `missing` points NEURAXIS_BIN at a path that does not exist, so no
    #: invocation is recorded and the `called` rule does not apply to it.
    runs_gate: bool = True


_SCENARIOS: tuple[_Scenario, ...] = (
    _Scenario(
        "allow",
        "positive control - a caller that refuses everything is an outage, not a gate client",
        PROCEED, 0, json.dumps(_ALLOW_VERDICT, sort_keys=True),
    ),
    _Scenario(
        "deny",
        "the gate blocked - DENY is the decision every caller gets right",
        REFUSE, 10, _verdict("DENY"),
    ),
    _Scenario(
        "escalate",
        "test for zero, not for 10 - ESCALATE is a block and does not license the lease",
        REFUSE, 11, _verdict("ESCALATE"),
    ),
    _Scenario(
        "wait_for_authority",
        "test for zero, not for 10 - WAIT_FOR_AUTHORITY is a block",
        REFUSE, 12, _verdict("WAIT_FOR_AUTHORITY"),
    ),
    _Scenario(
        "delegate",
        "test for zero, not for 10 - DELEGATE names someone else, it does not license this one",
        REFUSE, 13, _verdict("DELEGATE"),
    ),
    _Scenario(
        "fault",
        "a gate that could not answer has not answered - exit 2 refuses the lease",
        REFUSE, 2, "", "error: registry failed to load: neuraxis.yaml not found\n",
    ),
    _Scenario(
        "unknown_exit",
        "an unrecognised exit code must not read as unblocked - refusing is the only safe reading",
        REFUSE, 47, "",
    ),
    _Scenario(
        "contradiction",
        "exit code and verdict must agree - when they disagree no verdict from that run is usable",
        REFUSE, 0, _verdict("DENY"),
    ),
    _Scenario(
        "silent",
        "an exit 0 with no verdict is not an ALLOW - there is nothing to record against the lease",
        REFUSE, 0, "",
    ),
    _Scenario(
        "missing",
        "no gate reachable is not a gate that consented",
        REFUSE, 0, "", "", runs_gate=False,
    ),
)

#: Scenario names, in the order the suite drives them.
CALLER_SCENARIOS: tuple[str, ...] = tuple(s.name for s in _SCENARIOS)

_STUB = '''\
import json, os, pathlib, sys
here = pathlib.Path(__file__).parent
spec = json.loads((here / "spec.json").read_text(encoding="utf-8"))
try:
    payload = sys.stdin.read()
except Exception:
    payload = ""
with (here / "invocations.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "stdin": payload}) + "\\n")
sys.stdout.write(spec["stdout"])
sys.stderr.write(spec["stderr"])
sys.exit(spec["exit_code"])
'''


@dataclass(frozen=True)
class CallerCheck:
    """One rule applied to the caller, and whether it held."""

    scenario: str
    rule: str
    ok: bool
    detail: str
    expected: str | None = None
    observed: str | None = None
    exit_code: int | None = None
    invocations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "rule": self.rule,
            "ok": self.ok,
            "detail": self.detail,
            "expected": self.expected,
            "observed": self.observed,
            "exit_code": self.exit_code,
            "invocations": self.invocations,
        }


@dataclass(frozen=True)
class CallerReport:
    """Whether a caller may be trusted to act on what the gate returns."""

    caller: str
    checks: tuple[CallerCheck, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def conforms(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    @property
    def failures(self) -> tuple[CallerCheck, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller": self.caller,
            "conforms": self.conforms,
            "checks": [c.to_dict() for c in self.checks],
            "failures": [c.scenario for c in self.failures],
            "warnings": list(self.warnings),
        }


@dataclass
class _Run:
    exit_code: int | None
    observed: str
    invocations: tuple[Mapping[str, Any], ...]
    stderr: str = ""


def _drive(argv: list[str], scenario: _Scenario, timeout: float) -> _Run:
    with tempfile.TemporaryDirectory(prefix="neuraxis-caller-") as tmp:
        root = Path(tmp)
        stub = root / "gate_stub.py"
        stub.write_text(_STUB, encoding="utf-8")
        (root / "spec.json").write_text(
            json.dumps(
                {
                    "exit_code": scenario.exit_code,
                    "stdout": scenario.stdout,
                    "stderr": scenario.stderr,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        env = dict(os.environ)
        if scenario.runs_gate:
            env["NEURAXIS_BIN"] = sys.executable
            env["NEURAXIS_BIN_ARGS"] = json.dumps([str(stub)])
        else:
            env["NEURAXIS_BIN"] = str(root / "no-such-gate")
            env["NEURAXIS_BIN_ARGS"] = "[]"
        # Informational only. A caller that branches on it is testing its way
        # past the suite rather than through it, which no harness can prevent
        # and which is worth naming rather than pretending otherwise.
        env["NEURAXIS_CONFORMANCE_SCENARIO"] = scenario.name

        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(REFERENCE_REQUEST, sort_keys=True),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ConformanceError(f"caller not found: {exc}") from None
        except subprocess.TimeoutExpired:
            return _Run(None, NO_ANSWER, _read_invocations(root))
        except OSError as exc:
            raise ConformanceError(f"could not run the caller: {exc}") from None

        observed = PROCEED if completed.returncode == 0 else REFUSE
        return _Run(
            completed.returncode, observed, _read_invocations(root), completed.stderr[:500]
        )


def _read_invocations(root: Path) -> tuple[Mapping[str, Any], ...]:
    path = root / "invocations.jsonl"
    if not path.exists():
        return ()
    records: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, Mapping):
            records.append(record)
    return tuple(records)


def _fidelity_faults(invocations: Sequence[Mapping[str, Any]]) -> list[str]:
    """What the gate was actually asked, compared with what the caller was handed."""
    if not invocations:
        return ["the caller never invoked the gate, so there is nothing to compare"]

    raw = str(invocations[-1].get("stdin", "")).strip()
    if not raw:
        return [
            "the caller invoked the gate with nothing on stdin; the request never "
            "reached it"
        ]
    try:
        sent = json.loads(raw)
    except ValueError as exc:
        return [f"what the caller sent the gate is not JSON: {exc}"]
    if not isinstance(sent, Mapping):
        return ["what the caller sent the gate is not a JSON object"]

    faults: list[str] = []
    try:
        AuthorityRequest.from_dict(sent)
    except (ValueError, TypeError) as exc:
        faults.append(f"the gate would have refused the request as malformed: {exc}")

    for name in _FIDELITY_FIELDS:
        expected = REFERENCE_REQUEST[name]
        if name not in sent:
            faults.append(
                f"{name!r} was dropped on the way to the gate"
                + (
                    "; the gate cannot enforce verifier independence over a field it "
                    "was never sent"
                    if name == "verifier"
                    else ""
                )
            )
            continue
        actual = sent[name]
        if isinstance(expected, str) and isinstance(actual, str):
            if actual.strip().casefold() != expected.strip().casefold():
                faults.append(f"{name!r} reached the gate as {actual!r}, not {expected!r}")
        elif actual != expected:
            faults.append(f"{name!r} reached the gate as {actual!r}, not {expected!r}")
    return faults


def check_caller(
    command: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> CallerReport:
    """Drive `command` through the scenarios and apply the caller rules.

    `command` is argv, not a command line, for the reason `check_source` gives:
    splitting one is platform-specific, and a Windows path that loses its
    backslashes reads as a missing caller rather than a failing one.
    """
    if isinstance(command, (str, bytes)):
        raise ConformanceError(
            "pass the caller as a list of arguments, not a command line. Splitting one "
            "is platform-specific: a Windows path would lose its backslashes and the "
            "caller would read as missing rather than as failing"
        )
    argv = [str(part) for part in command]
    if not argv:
        raise ConformanceError("no caller command given")

    checks: list[CallerCheck] = []
    warnings: list[str] = []
    runs: dict[str, _Run] = {}

    for scenario in _SCENARIOS:
        run = _drive(argv, scenario, timeout)
        runs[scenario.name] = run
        if run.observed == NO_ANSWER:
            detail = (
                f"the caller did not answer within {timeout:g}s. A lease issuer that "
                "hangs has not refused; it has stopped"
            )
            ok = False
        elif run.observed == scenario.expect:
            detail = (
                f"{scenario.expect} the lease, which is the rule"
                if scenario.expect == REFUSE
                else "issued the lease, so the caller is capable of issuing one"
            )
            ok = True
        else:
            detail = (
                f"{run.observed} the lease where it should have {scenario.expect}"
                + (f"; stderr: {run.stderr.strip()[:160]}" if run.stderr.strip() else "")
            )
            ok = False
        checks.append(
            CallerCheck(
                scenario=scenario.name,
                rule=scenario.rule,
                ok=ok,
                detail=detail,
                expected=scenario.expect,
                observed=run.observed,
                exit_code=run.exit_code,
                invocations=len(run.invocations),
            )
        )

    # --- called: every issuance asks. A cached ALLOW is invisible from the
    # exit code, and it is precisely the bypass D-03 forbids.
    silent_scenarios = [
        s.name for s in _SCENARIOS if s.runs_gate and not runs[s.name].invocations
    ]
    checks.append(
        CallerCheck(
            scenario="called",
            rule="every issuance asks - a lease granted without calling the gate is the "
            "D-03 bypass, and the exit code cannot show it",
            ok=not silent_scenarios,
            detail=(
                "the gate was invoked in every scenario that offered one"
                if not silent_scenarios
                else "the caller issued or refused without invoking the gate in: "
                + ", ".join(silent_scenarios)
            ),
            invocations=sum(len(runs[s.name].invocations) for s in _SCENARIOS if s.runs_gate),
        )
    )

    # --- fidelity: the gate answers the question it was asked.
    faults = _fidelity_faults(runs["allow"].invocations)
    checks.append(
        CallerCheck(
            scenario="fidelity",
            rule="the gate sees the request the caller was asked to authorise - a field "
            "dropped in transit is a check silently switched off",
            ok=not faults,
            detail="; ".join(faults) or "every field reached the gate unchanged",
            invocations=len(runs["allow"].invocations),
        )
    )

    extra = [s.name for s in _SCENARIOS if s.runs_gate and len(runs[s.name].invocations) > 1]
    if extra:
        warnings.append(
            "the caller invoked the gate more than once in: "
            + ", ".join(extra)
            + ". Retrying a gate decision is not wrong, but a retry loop around a DENY "
            "is a bypass with a delay in it - check which"
        )

    return CallerReport(caller=" ".join(argv), checks=tuple(checks), warnings=tuple(warnings))
