"""Conformance suite for attestation sources.

The four provider rules -- fail closed, positive control, no vacuous probe,
emit an evidence reference -- are enforced today by `providers/harness.py`, for
providers that live in this repository. The controls that matter most will not:
GV-08's probe is written by the external assurance account, GV-02's and GV-06's
by L0, GV-07's by BADF. Until now there was no way for any of them to show
their source conforms before it was trusted, which is how a programme ends up
having trusted an attestation source nobody tested.

So this is the black-box half: a source is an executable, the suite drives it
through four scenarios, and the rules are applied to what comes back. Being an
executable rather than a Python object is the point -- the assurance account
should not have to write Python to prove its probe is honest.

**The contract.** The source reads one JSON object on stdin and writes one JSON
attestation to stdout:

    in   {"control": "GV-08", "scenario": "live"}
    out  {"control": "GV-08", "result": true,
          "issued_at": "2026-09-16T09:00:00+00:00",
          "issuer": "assurance-account/probe",
          "evidence_ref": "https://.../run/1234#step-7"}

The four scenarios, and what each one is for:

| scenario | the source should | rule |
|---|---|---|
| `live` | run normally | the output must parse, and carry a real evidence reference |
| `broken` | run with something it depends on unavailable | fail closed: never PASS |
| `negative` | run against a condition it should reject | positive control: it must be *able* to fail |
| `powerless` | run as an identity with no authority | vacuity: a probe that passes for a powerless identity is not a probe |

`powerless` is required only for sources whose control is declared `kind: probe`
in the registry. **The kind comes from the kernel, not from the source.** A
source that could declare its own kind could declare its way out of the vacuity
check, which is the whole finding class this package keeps rediscovering; and
the field defaults to `probe`, so omitting it tightens rather than relaxes.

**What conformance is not.** Every scenario is implemented by the source: it
decides what "broken" and "negative" mean for itself. So passing this proves a
source *can* fail and *does* carry evidence -- not that it fails when it should.
It raises the floor under an attestation source. It is not a proof that the
source is honest, and no black-box suite could be. The thing that would make it
one is the same thing as everywhere else here: KBS-001 T1.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from .errors import NeuraxisError

__all__ = [
    "SCENARIOS",
    "ConformanceError",
    "ConformanceReport",
    "ScenarioResult",
    "check_source",
    "scenarios_for",
]

#: Scenario names, in the order the suite drives them.
SCENARIOS = ("live", "broken", "negative", "powerless")

#: Evidence references that are not references. A source emitting one of these
#: has satisfied the letter of rule 4 and none of it.
_EMPTY_EVIDENCE = frozenset({"", "-", "n/a", "na", "none", "null", "ok", "pass", "fail", "true"})

DEFAULT_TIMEOUT = 30.0


class ConformanceError(NeuraxisError):
    """The suite could not be run at all: no source, bad arguments, bad control."""


def scenarios_for(kind: str) -> tuple[str, ...]:
    """Which scenarios a source for a control of this kind must implement.

    `probe` carries the vacuity scenario; `audit` does not, because an audit of
    a log legitimately returns the same answer whoever asks. Anything else is
    treated as `probe`: an unrecognised kind must not be a way out of a check.
    """
    if str(kind).strip().lower() == "audit":
        return ("live", "broken", "negative")
    return SCENARIOS


@dataclass(frozen=True)
class ScenarioResult:
    """What one scenario produced, and whether it satisfied its rule."""

    scenario: str
    rule: str
    ok: bool
    detail: str
    #: PASS / FAIL / None when the source produced no usable attestation.
    result: bool | None = None
    evidence_ref: str | None = None
    exit_code: int | None = None
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "rule": self.rule,
            "ok": self.ok,
            "detail": self.detail,
            "result": self.result,
            "evidence_ref": self.evidence_ref,
            "exit_code": self.exit_code,
        }


@dataclass(frozen=True)
class ConformanceReport:
    """Whether a source may be trusted to attest a control."""

    source: str
    control: str
    kind: str
    results: tuple[ScenarioResult, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def conforms(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    @property
    def failures(self) -> tuple[ScenarioResult, ...]:
        return tuple(r for r in self.results if not r.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "control": self.control,
            "kind": self.kind,
            "conforms": self.conforms,
            "scenarios": [r.to_dict() for r in self.results],
            "failures": [r.scenario for r in self.failures],
            "warnings": list(self.warnings),
        }


@dataclass
class _Run:
    """One invocation of the source."""

    exit_code: int
    stdout: str
    stderr: str
    attestation: Mapping[str, Any] | None = None
    parse_error: str = ""
    evidence_ref: str | None = None
    result: bool | None = None
    faults: list[str] = field(default_factory=list)


def _invoke(command: Sequence[str], control: str, scenario: str, timeout: float) -> _Run:
    payload = json.dumps({"control": control, "scenario": scenario}, sort_keys=True)
    try:
        completed = subprocess.run(
            list(command),
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConformanceError(f"source not found: {exc}") from None
    except subprocess.TimeoutExpired:
        # A source that hangs has not emitted PASS, so it has not failed open.
        # It is still unusable, which the caller needs told.
        return _Run(exit_code=-1, stdout="", stderr="", faults=[f"timed out after {timeout:g}s"])
    except OSError as exc:
        raise ConformanceError(f"could not run the source: {exc}") from None

    run = _Run(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    text = completed.stdout.strip()
    if not text:
        run.parse_error = "the source wrote nothing to stdout"
        return run
    try:
        payload_out = json.loads(text)
    except ValueError as exc:
        run.parse_error = f"stdout is not JSON: {exc}"
        return run
    if not isinstance(payload_out, Mapping):
        run.parse_error = "stdout is not a JSON object"
        return run

    run.attestation = payload_out
    raw_result = payload_out.get("result")
    if isinstance(raw_result, bool):
        run.result = raw_result
    else:
        # Strict, for the reason `rollback_tested` is strict: the string
        # "false" is truthy, so a source could report a pass by spelling it.
        run.parse_error = (
            f"'result' must be a JSON boolean, got {type(raw_result).__name__} "
            f"({raw_result!r})"
        )
    ref = payload_out.get("evidence_ref")
    if isinstance(ref, str):
        run.evidence_ref = ref.strip()
    return run


def _evidence_fault(run: _Run) -> str | None:
    if run.attestation is None:
        return None
    ref = run.evidence_ref
    if ref is None:
        return "no 'evidence_ref' field"
    if ref.lower() in _EMPTY_EVIDENCE:
        return f"evidence_ref {ref!r} is a verdict, not a reference"
    return None


def _timestamp_fault(run: _Run) -> str | None:
    if run.attestation is None:
        return None
    raw = run.attestation.get("issued_at")
    if not isinstance(raw, str) or not raw.strip():
        return "no 'issued_at' timestamp"
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return f"'issued_at' is not an ISO-8601 timestamp: {raw!r}"
    if parsed.tzinfo is None:
        return "'issued_at' carries no timezone; freshness would be judged in the reader's zone"
    return None


def check_source(
    command: Sequence[str],
    control: str,
    *,
    kind: str = "probe",
    timeout: float = DEFAULT_TIMEOUT,
) -> ConformanceReport:
    """Drive `command` through its scenarios and apply the four provider rules.

    `command` is argv, not a command line. Splitting a command line correctly
    is platform-specific -- `shlex` treats a backslash as an escape, so a
    Windows path silently becomes a different path and the source is reported
    as missing rather than as non-conforming. A string is refused rather than
    guessed at.
    """
    if isinstance(command, (str, bytes)):
        raise ConformanceError(
            "pass the source as a list of arguments, not a command line. Splitting one "
            "is platform-specific: a Windows path would lose its backslashes and the "
            "source would read as missing rather than as failing"
        )
    argv = [str(part) for part in command]
    if not argv:
        raise ConformanceError("no source command given")
    if not str(control).strip():
        raise ConformanceError("no control given")

    shown = " ".join(argv)
    required = scenarios_for(kind)
    results: list[ScenarioResult] = []
    warnings: list[str] = []
    runs: dict[str, _Run] = {}

    for scenario in required:
        runs[scenario] = _invoke(argv, control, scenario, timeout)

    # --- live: rule 4, and the output has to be usable at all.
    live = runs["live"]
    live_faults = [f for f in (live.parse_error, _timestamp_fault(live), _evidence_fault(live)) if f]
    live_faults += live.faults
    declared = live.attestation.get("control") if live.attestation else None
    if live.attestation is not None and declared != control:
        live_faults.append(f"attested {declared!r}, not the control it was asked about ({control})")
    results.append(
        ScenarioResult(
            scenario="live",
            rule="rule 4 - emit an evidence reference, never a bare pass/fail",
            ok=not live_faults,
            detail="; ".join(live_faults) or "emits a parseable attestation with a real reference",
            result=live.result,
            evidence_ref=live.evidence_ref,
            exit_code=live.exit_code,
            raw=live.stdout[:500],
        )
    )

    # --- broken: rule 1. Anything other than PASS is conforming; a crash
    # conforms but is worth saying out loud, because the caller has to be the
    # one converting it to FAIL.
    broken = runs["broken"]
    if broken.result is True:
        detail = "reported PASS with a dependency unavailable"
    elif broken.result is False:
        detail = "reported FAIL, which is the rule"
    else:
        detail = "produced no usable attestation, which the caller must treat as FAIL"
        warnings.append(
            "the 'broken' scenario crashed or emitted nothing rather than reporting FAIL. "
            "That fails closed only because every caller converts it; a source that says "
            "FAIL is better than one that says nothing"
        )
    results.append(
        ScenarioResult(
            scenario="broken",
            rule="rule 1 - fail closed: any unexpected condition is FAIL, never PASS",
            ok=broken.result is not True,
            detail=detail,
            result=broken.result,
            evidence_ref=broken.evidence_ref,
            exit_code=broken.exit_code,
            raw=broken.stdout[:500],
        )
    )

    # --- negative: rule 2. A source that cannot fail is not a check.
    negative = runs["negative"]
    results.append(
        ScenarioResult(
            scenario="negative",
            rule="rule 2 - positive control: prove the check is live before scoring a pass",
            ok=negative.result is False,
            detail=(
                "reports FAIL against a condition it should reject"
                if negative.result is False
                else "did not report FAIL against a condition it should reject; "
                "a source that cannot fail is not a check"
            ),
            result=negative.result,
            evidence_ref=negative.evidence_ref,
            exit_code=negative.exit_code,
            raw=negative.stdout[:500],
        )
    )

    # --- powerless: rule 3, probes only.
    if "powerless" in required:
        powerless = runs["powerless"]
        vacuous = live.result is True and powerless.result is True
        results.append(
            ScenarioResult(
                scenario="powerless",
                rule="rule 3 - no vacuous probe: the same answer for a powerful and a "
                "powerless identity is not a check",
                ok=not vacuous,
                detail=(
                    "passes for an identity with no authority, exactly as it does for one "
                    "with authority; the probe is not probing anything"
                    if vacuous
                    else "distinguishes a powerless identity from a powerful one"
                ),
                result=powerless.result,
                evidence_ref=powerless.evidence_ref,
                exit_code=powerless.exit_code,
                raw=powerless.stdout[:500],
            )
        )
    else:
        warnings.append(
            f"{control} is declared kind 'audit', so the vacuity scenario was not required. "
            "An audit of a log legitimately answers the same whoever asks - but the kind "
            "comes from the registry, so check it is the right one there"
        )

    return ConformanceReport(
        source=shown,
        control=str(control).strip(),
        kind=str(kind).strip().lower() or "probe",
        results=tuple(results),
        warnings=tuple(warnings),
    )
