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
import secrets
import socketserver
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .conformance import ConformanceError
from .model import REQUEST_REQUIRED_FIELDS, AuthorityRequest, now_utc

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


#: How a scenario configures the gate the caller will find.
_GATE_SERVED = "served"
_GATE_MISSING = "missing"
_GATE_UNSET = "unset"

# There is deliberately no principal-folding here, and the reason is a
# correction to this module's own previous fix.
#
# The first cut applied `strict_principal` to principal fields, reasoning that
# equality certifies the caller and this package reserves the strict fold for
# comparisons where equality authorises. That rule is about deciding whether
# two names denote the same PRINCIPAL. This comparison is not that question: it
# asks whether the bytes the gate received are the bytes the caller was handed,
# and any normalisation is a place where a difference gets excused. It was also
# not strictly safer -- two names both carrying invisible codepoints both fold
# to "" and compare EQUAL, which plain comparison catches.
#
# So fidelity compares exactly, with no strip and no fold. A faithful caller
# forwards what it was given; it has nothing to normalise.

#: Fields a faithful caller may legitimately stamp on the way through, and the
#: only ones exempt from the added-field rule. They are VALIDATED rather than
#: waived: `requested_at` was previously subtracted from the added set and never
#: reached the value loop either, making it the one key a caller could inject
#: with any content at all -- including a timestamp chosen to sit inside a
#: change freeze or outside a replay window.
_STAMPABLE = ("requested_at",)

#: How far a stamped `requested_at` may sit from now.
_STAMP_DRIFT_SECONDS = 300.0

#: What a faithful caller puts on the gate's command line, beyond the leading
#: arguments the harness supplied through NEURAXIS_BIN_ARGS.
_EXPECTED_GATE_ARGV = ("--json", "gate", "-")
_EXPECTED_GATE_FLAGS = frozenset({"--json", "-"})


def _mint_request() -> dict[str, Any]:
    """A fresh reference request for one run.

    `REFERENCE_REQUEST` is a module constant, so a caller could recognise the
    harness by its stdin and hardcode against it. The principal names carry a
    per-run suffix; everything structural -- the scope, the risk, and the fact
    that `verifier` equals `identity` -- is fixed, because those are what the
    scenarios reason about.
    """
    tag = secrets.token_hex(4)
    principal = f"agent-motor-{tag}"
    request = dict(REFERENCE_REQUEST)
    request["identity"] = principal
    request["verifier"] = principal
    request["intent"] = f"{REFERENCE_REQUEST['intent']} ({tag})"
    return request


@dataclass
class _Scenario:
    name: str
    rule: str
    expect: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    gate: str = _GATE_SERVED
    #: The request this scenario hands the caller. Minted on first use so it
    #: differs per run, and held so the fidelity comparison comes from the same
    #: object the caller was given.
    request_override: dict[str, Any] | None = None
    #: When set, the scripted gate ALLOWS a request that has had these fields
    #: removed and DENIES the faithful one. A fixed-answer gate can never
    #: observe doctoring, because nothing the caller does to the request
    #: changes what comes back.
    allow_if_missing: tuple[str, ...] = ()

    @property
    def offers_a_gate(self) -> bool:
        return self.gate == _GATE_SERVED

    def request(self) -> Mapping[str, Any]:
        if self.request_override is None:
            self.request_override = _mint_request()
        return self.request_override

    def responder(self):
        if not self.allow_if_missing:
            def fixed(_request: Mapping[str, Any]) -> dict[str, Any]:
                return {
                    "exit_code": self.exit_code,
                    "stdout": self.stdout,
                    "stderr": self.stderr,
                }
            return fixed

        wanted = self.allow_if_missing

        def trap(request: Mapping[str, Any]) -> dict[str, Any]:
            try:
                sent = json.loads(str(request.get("stdin", "")) or "{}")
            except ValueError:
                sent = {}
            doctored = isinstance(sent, Mapping) and any(f not in sent for f in wanted)
            if doctored:
                return {
                    "exit_code": 0,
                    "stdout": json.dumps(_ALLOW_VERDICT, sort_keys=True),
                    "stderr": "",
                }
            return {"exit_code": 10, "stdout": _verdict("DENY"), "stderr": ""}

        return trap


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
        REFUSE, 0, "", "", gate=_GATE_MISSING,
    ),
    _Scenario(
        "unconfigured",
        "an unconfigured gate is not an absent objection - the production default "
        "is that nothing has been set yet, and that branch has to refuse too",
        REFUSE, 0, "", "", gate=_GATE_UNSET,
    ),
    _Scenario(
        "allow_verdict_nonzero_exit",
        "exit code and verdict must agree, in BOTH directions - a caller that reads only "
        "the verdict issues on a gate that printed one and then died",
        REFUSE, 11, json.dumps(_ALLOW_VERDICT, sort_keys=True),
    ),
    _Scenario(
        "fidelity_trap",
        "doctoring the request is refusing to take the answer - the gate allows only "
        "a request with `verifier` removed, so a caller that retries without it issues",
        REFUSE, 10, "", "", allow_if_missing=("verifier",),
    ),
)

#: Scenario names, in the order the suite drives them.
CALLER_SCENARIOS: tuple[str, ...] = tuple(s.name for s in _SCENARIOS)

#: The scripted gate. It carries no answers and writes no evidence: it relays
#: the request to the harness and relays the harness's reply back.
#:
#: The previous design wrote the scenario's answer and the invocation log into
#: a directory whose path the harness handed to the caller in
#: NEURAXIS_BIN_ARGS. A caller could therefore read the answer without asking,
#: forge the log, and score twelve out of twelve having never executed a gate.
#: Everything the suite treated as evidence was writable by the thing being
#: measured. An adversarial review built exactly that caller.
#:
#: The caller can still read this source and find the port, and that is fine:
#: to learn the verdict it must now *make the request*, and the harness -- not
#: a file within the caller's reach -- is what records that it did.
_STUB = r"""
import json, socket, sys
port = int(sys.argv[1])
try:
    payload = sys.stdin.read()
except Exception:
    payload = ""
sock = socket.create_connection(("127.0.0.1", port), timeout=30)
try:
    sock.sendall(json.dumps({"stdin": payload, "argv": sys.argv[2:]}).encode("utf-8"))
    sock.shutdown(socket.SHUT_WR)
    buf = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
finally:
    sock.close()
reply = json.loads(buf.decode("utf-8"))
sys.stdout.write(reply["stdout"])
sys.stderr.write(reply["stderr"])
sys.exit(reply["exit_code"])
"""


class _GateHandler(socketserver.StreamRequestHandler):
    timeout = 30

    def handle(self) -> None:
        raw = self.rfile.read()
        try:
            request = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            request = {"stdin": "", "argv": [], "unparseable": True}
        if not isinstance(request, Mapping):
            request = {"stdin": "", "argv": [], "unparseable": True}
        server = self.server
        server.record(request)
        self.wfile.write(json.dumps(server.respond(request)).encode("utf-8"))


class _GateServer(socketserver.ThreadingTCPServer):
    """The scripted gate, running inside the harness.

    Two properties the file-based stub could not have:

    **The invocation log is server-side.** A caller cannot append to it, cannot
    truncate it, and cannot learn a verdict without producing a record.

    **The reply can depend on the request.** That is what makes a caller's
    *doctoring* observable. The `fidelity_trap` scenario allows a request that
    has had `verifier` removed and denies the faithful one, so a caller that
    retries without the field visibly issues where it must refuse -- a property
    no fixed-answer stub can test, because nothing a caller does to the request
    changes what comes back.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, respond) -> None:
        super().__init__(("127.0.0.1", 0), _GateHandler)
        self.respond = respond
        self.records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, request: Mapping[str, Any]) -> None:
        with self._lock:
            self.records.append(dict(request))

    def seen(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(self.records)

    @property
    def port(self) -> int:
        return int(self.server_address[1])


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
    server = _GateServer(scenario.responder())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="neuraxis-caller-") as tmp:
            stub = Path(tmp) / "gate_stub.py"
            stub.write_text(_STUB, encoding="utf-8")

            env = dict(os.environ)
            if scenario.gate == _GATE_UNSET:
                # The production default: nothing configured. Never exercised
                # before, and it is the one branch every caller takes before
                # somebody sets the variable.
                env.pop("NEURAXIS_BIN", None)
                env.pop("NEURAXIS_BIN_ARGS", None)
            elif scenario.gate == _GATE_MISSING:
                env["NEURAXIS_BIN"] = str(Path(tmp) / "no-such-gate")
                env["NEURAXIS_BIN_ARGS"] = "[]"
            else:
                env["NEURAXIS_BIN"] = sys.executable
                env["NEURAXIS_BIN_ARGS"] = json.dumps([str(stub), str(server.port)])
            # NEURAXIS_CONFORMANCE_SCENARIO used to be set here, "informational
            # only", defended with the argument that no black-box harness can
            # stop a caller fingerprinting it. That argument is true and was
            # applied to the wrong thing. Fingerprinting is hard to prevent;
            # handing the subject a variable whose value IS the expected answer
            # is not the same problem. Exactly one scenario expects PROCEED, so
            #     exit(0 if $NEURAXIS_CONFORMANCE_SCENARIO == "allow" else 1)
            # was a complete oracle for all twelve checks, and in production --
            # where the variable is unset -- that caller issues every lease
            # unconditionally. It had no consumer. It is gone.

            try:
                completed = subprocess.run(
                    argv,
                    input=json.dumps(scenario.request(), sort_keys=True),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise ConformanceError(f"caller not found: {exc}") from None
            except subprocess.TimeoutExpired:
                return _Run(None, NO_ANSWER, server.seen())
            except OSError as exc:
                raise ConformanceError(f"could not run the caller: {exc}") from None

            observed = PROCEED if completed.returncode == 0 else REFUSE
            return _Run(
                completed.returncode, observed, server.seen(), completed.stderr[:500]
            )
    finally:
        server.shutdown()
        server.server_close()


def _sent(record: Mapping[str, Any]) -> Mapping[str, Any] | str:
    """What one invocation put on the gate's stdin, parsed, or why it could not be."""
    raw = str(record.get("stdin", "")).strip()
    if not raw:
        return "invoked the gate with nothing on stdin; the request never reached it"
    try:
        sent = json.loads(raw)
    except ValueError as exc:
        return f"what the caller sent the gate is not JSON: {exc}"
    if not isinstance(sent, Mapping):
        return "what the caller sent the gate is not a JSON object"
    return sent


def _check_stamp(name: str, value: Any) -> str | None:
    """A field a caller may add is validated, not waived."""
    if name != "requested_at":
        return f"{name!r} is stampable but has no validator"
    if not isinstance(value, str):
        return f"'requested_at' must be a string, got {type(value).__name__}"
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return f"'requested_at' is not an ISO-8601 timestamp: {value!r}"
    if parsed.tzinfo is None:
        return "'requested_at' carries no timezone"
    drift = abs((parsed - now_utc()).total_seconds())
    if drift > _STAMP_DRIFT_SECONDS:
        return (
            f"'requested_at' is {drift / 60:.0f} minutes from now; a caller that chooses "
            "the clock chooses which freeze window and which replay horizon it is inside"
        )
    return None


def _compare_argv(argv: Sequence[str], expected_leading: Sequence[str]) -> list[str]:
    """What the caller put on the gate's command line.

    Recorded since the harness gained a server and never compared. For a CLI
    gate the arguments carry at least as much authority as the body: a
    subcommand, a `--force`, a `--registry` pointing somewhere permissive.
    """
    if not argv:
        # The stub fills this from its own `sys.argv`, so an empty record means
        # whatever reached the server did not come through a gate invocation.
        # A caller that opens the socket itself, rather than executing
        # NEURAXIS_BIN, lands here.
        #
        # This detects the shortcut, not a determined impersonation: a caller
        # that also forges the argv is indistinguishable from the stub over a
        # socket, and separating them needs the peer's process identity, which
        # is T1-shaped. `called` is narrowed to what it can actually show.
        return [
            "reached the gate with no command line; nothing shows NEURAXIS_BIN was executed"
        ]
    missing = [a for a in expected_leading if a not in argv]
    if missing:
        return [f"invoked the gate without {', '.join(repr(a) for a in missing)}"]
    suspicious = [
        a for a in argv
        if a.startswith("-") and a not in _EXPECTED_GATE_FLAGS and a not in expected_leading
    ]
    if suspicious:
        return [f"passed {', '.join(repr(a) for a in suspicious)} on the gate's command line"]
    return []


def _compare(sent: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    """Every difference between what the gate was asked and what was handed over.

    Three things the first cut of this got wrong, each found by driving a real
    exploit through it:

    **Added fields count.** The original walked the expected field list and
    asked "was anything lost". The dangerous direction is the other one: a
    caller that appends `ratification_ref` clears the non-delegable floor and
    the GV-07 requirement, and every field it was handed did indeed arrive
    unchanged. Key sets are compared, not just values.

    **Everything compares exactly.** No strip, no fold. A faithful caller
    forwards what it was handed and has nothing to normalise, so any difference
    is a difference. An earlier cut folded principal fields with
    `strict_principal` on the grounds that equality certifies; that rule is
    about deciding whether two names denote the same principal, which is not
    the question here, and it was laxer in one case rather than safer.
    """
    faults: list[str] = []
    try:
        AuthorityRequest.from_dict(dict(sent))
    except (ValueError, TypeError) as exc:
        faults.append(f"the gate would have refused the request as malformed: {exc}")

    stamped = sorted(set(sent) & set(_STAMPABLE))
    for name in stamped:
        fault = _check_stamp(name, sent[name])
        if fault:
            faults.append(fault)

    added = sorted(set(sent) - set(expected) - set(_STAMPABLE))
    if added:
        faults.append(
            f"added {', '.join(repr(a) for a in added)} on the way to the gate"
            + (
                "; a ratification reference the caller invented satisfies the "
                "non-delegable floor the gate exists to hold"
                if "ratification_ref" in added
                else ""
            )
        )

    for name in expected:
        want = expected[name]
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
        got = sent[name]
        if type(got) is not type(want) or got != want:
            # `1 == True` in Python, so the type check comes first: a caller
            # that sends 1 for a boolean has not sent the boolean the gate
            # demands. And the comparison is exact, so `"  scope  "` is a
            # different scope -- it is what lands in the evidence record.
            faults.append(f"{name!r} reached the gate as {got!r}, not {want!r}")
    return faults


def _fidelity_faults(runs: Mapping[str, _Run], scenarios: Sequence[_Scenario]) -> list[str]:
    """Every invocation, in every scenario, against the request that scenario handed over.

    The first cut compared only the LAST invocation of the `allow` scenario.
    Two exploits walked through the gap: decide on a doctored first call and
    make a faithful decoy second one, or -- the caller a real team writes under
    schedule pressure -- ask faithfully, get DENY, then retry without
    `verifier` and honour that.
    """
    faults: list[str] = []
    asked_anywhere = False
    for scenario in scenarios:
        run = runs[scenario.name]
        expected = scenario.request()
        for index, record in enumerate(run.invocations, start=1):
            asked_anywhere = True
            sent = _sent(record)
            argv_faults = _compare_argv(
                [str(a) for a in (record.get("argv") or [])], _EXPECTED_GATE_ARGV
            )
            faults += [f"{scenario.name} call {index}: {f}" for f in argv_faults]
            if isinstance(sent, str):
                faults.append(f"{scenario.name} call {index}: {sent}")
                continue
            faults += [f"{scenario.name} call {index}: {f}" for f in _compare(sent, expected)]
    if not asked_anywhere:
        return ["the caller never invoked the gate, so there is nothing to compare"]
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

    # Scenarios are independent -- a separate scripted gate, a separate
    # subprocess, no shared state -- and each one costs two interpreter starts.
    # Run them concurrently; results are keyed by name, so the report's order
    # still comes from `_SCENARIOS`.
    with ThreadPoolExecutor(max_workers=min(len(_SCENARIOS), 8)) as pool:
        futures = {
            scenario.name: pool.submit(_drive, argv, scenario, timeout)
            for scenario in _SCENARIOS
        }
        runs: dict[str, _Run] = {name: future.result() for name, future in futures.items()}

    for scenario in _SCENARIOS:
        run = runs[scenario.name]
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
        s.name for s in _SCENARIOS if s.offers_a_gate and not runs[s.name].invocations
    ]
    checks.append(
        CallerCheck(
            scenario="called",
            rule="every issuance asks - a lease granted without calling the gate is the "
            "D-03 bypass, and the exit code cannot show it. This shows the caller "
            "CONSULTED the scripted gate; proving it EXECUTED the configured binary "
            "needs the peer's process identity, which does not exist until T1",
            ok=not silent_scenarios,
            detail=(
                "the gate was invoked in every scenario that offered one"
                if not silent_scenarios
                else "the caller issued or refused without invoking the gate in: "
                + ", ".join(silent_scenarios)
            ),
            invocations=sum(
                len(runs[s.name].invocations) for s in _SCENARIOS if s.offers_a_gate
            ),
        )
    )

    # --- fidelity: the gate answers the question it was asked.
    faults = _fidelity_faults(runs, _SCENARIOS)
    checks.append(
        CallerCheck(
            scenario="fidelity",
            rule="the gate sees the request the caller was asked to authorise, on every "
            "call in every scenario - a field dropped, altered or added in transit is a "
            "check silently switched off",
            ok=not faults,
            detail="; ".join(faults) or "every field reached the gate unchanged",
            invocations=sum(len(r.invocations) for r in runs.values()),
        )
    )

    extra = [
        s.name for s in _SCENARIOS if s.offers_a_gate and len(runs[s.name].invocations) > 1
    ]
    if extra:
        warnings.append(
            "the caller invoked the gate more than once in: "
            + ", ".join(extra)
            + ". Retrying a gate decision is not wrong, but a retry loop around a DENY "
            "is a bypass with a delay in it - check which"
        )

    return CallerReport(caller=" ".join(argv), checks=tuple(checks), warnings=tuple(warnings))
