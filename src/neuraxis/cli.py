"""Neuraxis CLI — the language-neutral contract.

Non-Python callers (maw-js agents, the L0 layer, CI) invoke the gate here and
read JSON from stdout plus an exit code. Exit codes are part of the contract:

    0   ALLOW / command succeeded
    10  DENY
    11  ESCALATE
    12  WAIT_FOR_AUTHORITY
    13  DELEGATE
    2   error (registry fault, bad input, unreadable attestations)

Note that every non-zero code blocks. A caller that treats only 10 as a block
will act on an ESCALATE, so callers must test for zero, not for a code list.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .attestation import AttestationStore
from .errors import NeuraxisError
from .envelope import Envelope, EnvelopeRegister
from .evidence import (
    DischargeRecord,
    EvidenceSink,
    audit_envelopes,
    audit_obligations,
    record_decision,
)
from .gate import GovernanceGate
from .model import (
    REQUEST_OPTIONAL_FIELDS,
    REQUEST_REQUIRED_FIELDS,
    Attestation,
    AuthorityRequest,
    Decision,
    Obligation,
    Risk,
    now_utc,
)
from .providers import ProviderOutcome, get_provider, providers_for, run_provider
from .providers.registry import UnknownProviderError, coverage
from .registry import load_registry, parse_duration, registry_digest
from .resolver import BandResolver
from .scorecard import measure
from .waiver import Waiver, WaiverRegister

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_BY_DECISION = {
    Decision.ALLOW: 0,
    Decision.DENY: 10,
    Decision.ESCALATE: 11,
    Decision.WAIT_FOR_AUTHORITY: 12,
    Decision.DELEGATE: 13,
}

DEFAULT_ATTESTATIONS = os.environ.get("NEURAXIS_ATTESTATIONS", "attestations.jsonl")


# ---- helpers -----------------------------------------------------------


def _load(args: argparse.Namespace) -> tuple[Any, AttestationStore]:
    registry = load_registry(args.registry)
    store = AttestationStore.from_file(args.attestations)
    return registry, store


def _load_waivers(args: argparse.Namespace, registry: Any) -> WaiverRegister:
    """Load the waiver file bound to this registry's policy.

    An absent file means no waivers, which is the correct default. A malformed
    one raises: a half-read waiver file would under-constrain the gate the same
    way a half-read registry would.
    """
    return WaiverRegister.for_registry(registry, path=getattr(args, "waivers", None))


def _load_envelopes(args: argparse.Namespace, registry: Any) -> EnvelopeRegister:
    """Load the envelope file bound to this registry's policy.

    An absent file means no envelopes, which denies every envelope-bounded
    capability. That is the correct reading of "declared in advance": the
    default is not permission.
    """
    return EnvelopeRegister.for_registry(registry, path=getattr(args, "envelopes_file", None))


def _force_utf8_io() -> None:
    """Emit UTF-8 whatever the console code page is.

    Windows consoles default to a legacy code page (cp1252/cp437) that cannot
    encode the em-dashes and box characters in provider and reason text, which
    turns readable output into mojibake. `errors="replace"` keeps a console
    that genuinely cannot render a glyph from crashing the command.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - console-dependent
            pass


def _window(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


def _adjustments(pairs: Sequence[str] | None) -> dict[str, float]:
    """Parse `--adjust key=value` pairs into numbers.

    A value that is not a number is an error rather than a string passed
    through: an envelope bounds magnitudes, and a bound that cannot be compared
    is not a bound.
    """
    out: dict[str, float] = {}
    for pair in pairs or ():
        key, sep, raw = str(pair).partition("=")
        if not sep or not key.strip():
            raise NeuraxisError(f"--adjust expects key=value, got {pair!r}")
        try:
            out[key.strip()] = float(raw)
        except ValueError:
            raise NeuraxisError(
                f"--adjust {key.strip()}={raw!r} is not a number"
            ) from None
    return out


def _emit(payload: dict[str, Any], *, as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif text is not None:
        print(text)


# ---- commands ----------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    sha, source = registry_digest(args.registry)
    orphans = [
        cid for cid, cap in registry.capabilities.items() if cap.band not in registry.bands
    ]
    ungranted = [bid for bid in registry.bands if not registry.roles_granting(bid)]
    payload = {
        "framework": registry.framework,
        "version": registry.version,
        "principle": registry.principle,
        "capabilities": len(registry.capabilities),
        "bands": len(registry.bands),
        "controls": len(registry.controls),
        "non_delegable": sorted(registry.non_delegable),
        "attestation_max_age_seconds": int(registry.attestation_max_age.total_seconds()),
        "windows": {
            cid: int(c.max_age.total_seconds()) for cid, c in registry.controls.items()
        },
        "enforcement_mode": registry.enforcement_mode,
        "on_missing_attestation": registry.on_missing_attestation,
        # The digest of the kernel config actually loaded. A release records
        # the same value, so "am I running the ratified registry?" is one
        # comparison rather than a judgement (KBS-001 K-09).
        "registry_path": str(source),
        "registry_sha256": sha,
        "warnings": (
            [f"band {b} is granted to no role" for b in ungranted]
            + [f"capability {c} has no band" for c in orphans]
            + (
                [
                    "authority.envelope_signers is empty: any principal other than the "
                    "bounded one may declare an envelope (ILR-001-DR D-01)"
                ]
                if any(c.envelope_bounded for c in registry.capabilities.values())
                and not registry.envelope_policy.signers_restricted
                else []
            )
        ),
        "valid": True,
    }
    lines = [
        f"{registry.framework} v{registry.version} ({registry.principle})",
        f"  {len(registry.capabilities)} capabilities across {len(registry.bands)} bands",
        f"  {len(registry.controls)} governance controls",
        f"  enforcement: {registry.enforcement_mode}, missing attestation -> {registry.on_missing_attestation}",
        f"  default attestation window: {registry.attestation_max_age}",
        "  windows:",
        *[
            f"    {c.id}  {c.name:<14} {_window(c.max_age)}"
            for c in registry.controls.values()
        ],
    ]
    lines.append(f"  registry:  {source}")
    lines.append(f"  sha256:    {sha}")
    lines += [f"  WARNING: {w}" for w in payload["warnings"]]
    lines.append("  registry valid")
    _emit(payload, as_json=args.json, text="\n".join(lines))
    return EXIT_OK


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _expected_digest(args: argparse.Namespace) -> str | None:
    """The digest to compare against, from a flag or a release asset.

    An expectation that cannot be read is an error, never a pass. A drift check
    that treats an unparseable expectation as "no drift" is the vacuous probe
    in its cheapest form: it reports clean for a file nobody could read.
    """
    if args.expect and args.expect_file:
        raise NeuraxisError("pass --expect or --expect-file, not both")
    raw = args.expect
    if args.expect_file:
        path = Path(args.expect_file)
        if not path.is_file():
            raise NeuraxisError(f"expectation file not found: {path}")
        raw = None
        for line in path.read_text(encoding="utf-8-sig").split("\n"):
            token = line.strip().lower()
            if token.startswith("sha256"):
                raw = token.split()[-1]
                break
            if _SHA256.match(token):
                raw = token
                break
        if raw is None:
            raise NeuraxisError(
                f"{path} contains no sha256 line; expected a REGISTRY-DIGEST.txt "
                "from a release, or a file holding a bare 64-character digest"
            )
    if raw is None:
        return None
    candidate = str(raw).strip().lower()
    if not _SHA256.match(candidate):
        raise NeuraxisError(
            f"{candidate!r} is not a sha256 digest (64 lowercase hex characters)"
        )
    return candidate


def cmd_drift(args: argparse.Namespace) -> int:
    """Compare the kernel registry on disk against its ratified digest.

    KBS-001 K-09. The registry is kernel; a release records the SHA-256 of the
    exact bytes that were ratified, and this asks whether the file the gate is
    about to load is that one.

    A mismatch is not automatically an incident. It means the kernel config on
    disk is not the one that was released, which is either a change nobody
    ratified or a version you did not think you were running. Both are worth
    knowing before the next decision is made on it.
    """
    registry = load_registry(args.registry)          # drift on an invalid registry is moot
    sha, source = registry_digest(args.registry)
    expected = _expected_digest(args)

    matches = None if expected is None else (sha == expected)
    payload = {
        "registry_path": str(source),
        "registry_sha256": sha,
        "registry_version": registry.version,
        "package_version": __version__,
        "expected_sha256": expected,
        "matches": matches,
    }
    lines = [
        f"registry:          {source}",
        f"sha256:            {sha}",
        f"registry version:  {registry.version}   (the config's own version, not the package's)",
        f"package version:   {__version__}",
    ]
    if expected is None:
        lines.append("")
        lines.append(
            "No expectation given, so nothing was compared. Pass --expect <sha256> or "
            "--expect-file REGISTRY-DIGEST.txt from the release you believe you are running."
        )
    elif matches:
        lines.append("")
        lines.append("MATCH: the registry on disk is the ratified one.")
    else:
        lines.append(f"expected: {expected}")
        lines.append("")
        lines.append(
            "DRIFT: the kernel registry on disk is not the ratified one. Either a change "
            "was made without a release, or this is not the version you think it is. "
            "Do not attest anything against it until that is resolved."
        )
    _emit(payload, as_json=args.json, text="\n".join(lines))
    if matches is False:
        return EXIT_BY_DECISION[Decision.DENY]
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    waivers = _load_waivers(args, registry)
    resolver = BandResolver(registry, store, waivers)
    # No claimed identities: this is a report of what the waiver set licenses
    # for someone, not an authority decision. `gate` is the licensing path and
    # always passes the requesting principal.
    statuses = resolver.all_statuses()

    payload = {
        "attestations_on_file": len(store),
        "waivers_active": [w.id for w in waivers.active()],
        "bands": {bid: st.to_dict() for bid, st in statuses.items()},
        "attained": [bid for bid, st in statuses.items() if st.attained],
        "conditional": [bid for bid, st in statuses.items() if st.conditional],
    }

    rows = ["BAND        STATUS        DETAIL"]
    for bid, st in statuses.items():
        if st.conditional:
            mark = "CONDITIONAL"
        elif st.attained:
            mark = "ATTAINED"
        else:
            mark = "BLOCKED"
        detail = st.reasons[0] if st.reasons else ""
        rows.append(f"{bid:<11} {mark:<13} {detail}")
    for line in waivers.triggers():
        rows.append("")
        rows.append(f"TRIGGER ARMED  {line}")
    if not store:
        rows.append("")
        rows.append(
            "No attestations on file: every band is blocked. This is the correct "
            "initial state, not a fault."
        )
    _emit(payload, as_json=args.json, text="\n".join(rows))
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    gate = GovernanceGate(
        registry, store, _load_waivers(args, registry), _load_envelopes(args, registry)
    )

    if args.request == "-":
        try:
            raw = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"error: stdin is not valid JSON: {exc}", file=sys.stderr)
            return EXIT_ERROR
        try:
            request = AuthorityRequest.from_dict(raw)
        except (ValueError, TypeError) as exc:
            print(f"error: invalid request: {exc}", file=sys.stderr)
            return EXIT_ERROR
    else:
        missing = [f for f in ("capability", "identity", "role", "intent") if not getattr(args, f)]
        if missing:
            print(
                f"error: --{', --'.join(missing)} required (or pass a JSON request on stdin with '-')",
                file=sys.stderr,
            )
            return EXIT_ERROR
        request = AuthorityRequest(
            intent=args.intent,
            identity=args.identity,
            role=args.role,
            capability=args.capability,
            scope=args.scope,
            risk=Risk(args.risk.upper()),
            verifier=args.verifier,
            rollback_tested=args.rollback_tested,
            ratification_ref=args.ratification_ref,
            envelope_ref=args.envelope_ref,
            adjustments=_adjustments(args.adjust),
        )

    verdict = gate.evaluate(request)

    # Record before reporting: a caller must never be told ALLOW for a decision
    # that left no trace, so the recording result is what gets reported.
    sink = EvidenceSink(args.evidence_sink) if args.evidence_sink else None
    verdict, record = record_decision(sink, request, verdict)

    if args.json:
        payload = verdict.to_dict()
        if record is not None:
            payload["verdict_id"] = record.verdict_id
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{verdict.decision.value} {verdict.capability} ({verdict.band or 'no band'})")
        if record is not None:
            print(f"  verdict {record.verdict_id}")
        for reason in verdict.reasons:
            print(f"  - {reason}")
        if verdict.obligations:
            print(f"  obligations: {', '.join(o.value for o in verdict.obligations)}")
        if verdict.waivers:
            print(f"  CONDITIONAL on waiver(s): {', '.join(verdict.waivers)}")
    return EXIT_BY_DECISION[verdict.decision]


def cmd_attest(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    if args.control not in registry.controls:
        print(f"error: unknown control {args.control}", file=sys.stderr)
        return EXIT_ERROR

    if args.from_provider:
        try:
            provider = get_provider(args.from_provider, log_path=args.task_log, gate_log_path=args.gate_log, lease_log_path=args.lease_log)
        except UnknownProviderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if provider.control != args.control:
            print(
                f"error: provider {provider.name} attests {provider.control}, not {args.control}",
                file=sys.stderr,
            )
            return EXIT_ERROR
        run = run_provider(provider)
        attestation = run.to_attestation()
        store.append_to_file(args.attestations, attestation)
        _emit(
            run.to_dict(),
            as_json=args.json,
            text=(
                f"{run.result.outcome.value} {run.control} via {run.provider}\n"
                f"  {run.result.detail}"
            ),
        )
        return EXIT_OK if run.attests else EXIT_BY_DECISION[Decision.DENY]

    if not args.result or not args.issuer or not args.evidence_ref:
        print(
            "error: --result, --issuer and --evidence-ref are required "
            "unless --from-provider is used",
            file=sys.stderr,
        )
        return EXIT_ERROR

    attestation = Attestation(
        control=args.control,
        result=(args.result == "pass"),
        issued_at=now_utc(),
        issuer=args.issuer,
        evidence_ref=args.evidence_ref,
    )
    store.append_to_file(args.attestations, attestation)
    payload = {
        "control": attestation.control,
        "result": "pass" if attestation.result else "fail",
        "issued_at": attestation.issued_at.isoformat(),
        "issuer": attestation.issuer,
        "evidence_ref": attestation.evidence_ref,
        "recorded_to": str(args.attestations),
    }
    _emit(
        payload,
        as_json=args.json,
        text=(
            f"recorded {attestation.control} "
            f"{'PASS' if attestation.result else 'FAIL'} "
            f"({attestation.evidence_ref}) -> {args.attestations}"
        ),
    )
    return EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    resolver = BandResolver(registry, store, _load_waivers(args, registry))
    attained = resolver.attained_bands()
    band = args.band or (attained[-1] if attained else next(iter(registry.bands)))
    required = registry.band(band).requires
    passing = len(required) - len(store.missing(required, registry.max_age_for))

    card = measure(
        bands_attained=len(attained),
        bands_total=len(registry.bands),
        exam_first_pass_rate=args.exam_pass_rate,
        lesson_yield=args.lesson_yield,
        retrieval_precision=args.retrieval_precision,
        tasks_completed=args.tasks_completed,
        tasks_attempted=args.tasks_attempted,
        independent_verification_coverage=args.verification_coverage,
        performer_is_verifier=args.performer_is_verifier,
        controls_passing=passing,
        controls_required=len(required),
    )
    permitted, reasons = card.gate_band(registry, band)
    payload = {"band": band, "scorecard": card.to_dict(), "permitted": permitted, "reasons": list(reasons)}
    lines = [f"scorecard for {band}"]
    lines += [f"  {k} = {v}" for k, v in card.to_dict().items() if k in ("C", "R", "L", "A", "V", "G")]
    lines.append(f"  effective = {card.effective:.4f}  (diagnostic only; do not report as a KPI)")
    lines.append(f"  {'PERMITTED' if permitted else 'BLOCKED'}")
    lines += [f"    - {r}" for r in reasons]
    _emit(payload, as_json=args.json, text="\n".join(lines))
    return EXIT_OK if permitted else EXIT_BY_DECISION[Decision.DENY]


def cmd_discharge(args: argparse.Namespace) -> int:
    """Record that one obligation of one verdict was met."""
    if not args.evidence_sink:
        print("error: --evidence-sink is required to discharge an obligation", file=sys.stderr)
        return EXIT_ERROR
    sink = EvidenceSink(args.evidence_sink)
    known = {r.get("verdict_id") for r in sink.read() if r.get("record") == "evidence"}
    if args.verdict not in known:
        print(
            f"error: no verdict {args.verdict} in {args.evidence_sink}; "
            "a discharge for a decision that was never issued is not evidence",
            file=sys.stderr,
        )
        return EXIT_ERROR

    discharge = DischargeRecord(
        verdict_id=args.verdict,
        obligation=args.obligation,
        at=now_utc(),
        by=args.by,
        evidence_ref=args.evidence_ref,
    )
    sink.append(discharge)
    _emit(
        discharge.to_dict(),
        as_json=args.json,
        text=f"discharged {args.obligation} for verdict {args.verdict} ({args.evidence_ref})",
    )
    return EXIT_OK


def cmd_obligations(args: argparse.Namespace) -> int:
    """Report what the gate's ALLOWs owe and what has been paid."""
    if not args.evidence_sink:
        print("error: --evidence-sink is required", file=sys.stderr)
        return EXIT_ERROR
    sink = EvidenceSink(args.evidence_sink)
    grace = parse_duration(args.grace) if args.grace else None
    audit = audit_obligations(sink.read(), grace=grace)

    lines = [
        f"{audit.allowed} ALLOW(s) owing {audit.owed} obligation(s); "
        f"{audit.discharged} discharged",
    ]
    for item in audit.outstanding:
        lines.append(
            f"  OUTSTANDING {item.obligation} — {item.capability} by {item.performer} "
            f"({item.verdict_id}, {item.at.isoformat()})"
        )
    for fault in audit.faults:
        lines.append(f"  FAULT {fault}")
    if audit.clean:
        lines.append("  every obligation owed has been discharged by another identity")
    lines.append(
        "  note: this reads a sink the audited party can also write. It is the record "
        "stream GV-03 protects, not an attestation of GV-03."
    )
    _emit(audit.to_dict(), as_json=args.json, text="\n".join(lines))
    return EXIT_OK if audit.clean else EXIT_BY_DECISION[Decision.DENY]


def cmd_envelopes(args: argparse.Namespace) -> int:
    """Report the bounded-tuning path: which bounds are declared, and by whom.

    With `--audit`, also counts out-of-envelope denials per envelope from the
    evidence sink and exits 10 when the ILR-001-DR D-01 reversal condition is
    armed.
    """
    registry, _ = _load(args)
    envelopes = _load_envelopes(args, registry)
    at = now_utc()
    bounded = sorted(c.id for c in registry.capabilities.values() if c.envelope_bounded)
    active_ids = {e.id for e in envelopes.active(at)}

    audit = None
    if args.audit:
        sink = EvidenceSink(args.evidence_sink) if args.evidence_sink else None
        # The generator is passed unconsumed so a malformed line becomes a
        # reported fault rather than an exception that aborts the audit.
        audit = audit_envelopes(sink.read() if sink else iter(()), at=at)

    payload = {
        "envelope_bounded_capabilities": bounded,
        "signers_restricted": registry.envelope_policy.signers_restricted,
        "signers": sorted(registry.envelope_policy.signers),
        "max_ttl": _window(registry.envelope_policy.max_ttl),
        "envelopes": [{**e.to_dict(), "active": e.id in active_ids} for e in envelopes],
        "audit": audit.to_dict() if audit else None,
    }

    lines = [
        f"envelope-bounded: {', '.join(bounded) or 'none'}",
        f"max_ttl={_window(registry.envelope_policy.max_ttl)}",
    ]
    if registry.envelope_policy.signers_restricted:
        lines.append(f"signers: {', '.join(sorted(registry.envelope_policy.signers))}")
    else:
        lines.append(
            "WARNING: authority.envelope_signers is empty, so any principal other "
            "than the bounded one may declare a bound. This is the weakest form "
            "the control takes; it closes when T1 issues real identities."
        )
    lines.append("")
    if not len(envelopes):
        lines.append("No envelopes on file. Every envelope-bounded capability is denied.")
    else:
        lines.append("ID                STATE     CAPABILITY  PRINCIPAL        EXPIRES")
        for e in envelopes:
            state = "ACTIVE" if e.id in active_ids else (
                "PENDING" if at < e.issued_at else "EXPIRED"
            )
            lines.append(
                f"{e.id:<17} {state:<9} {e.capability:<11} {e.principal:<16} "
                f"{e.expires_at.isoformat()}"
            )
            lines.append(f"    signed by: {e.signed_by}   manifest: {e.manifest_ref}")
            lines.append(f"    targets: {', '.join(e.targets)}")
            if e.limits:
                bounds = ", ".join(
                    f"{k}=[{v.low:g},{v.high:g}]" for k, v in sorted(e.limits.items())
                )
                lines.append(f"    limits: {bounds}")
    if audit is not None:
        lines.append("")
        if audit.clean:
            lines.append(
                f"No envelope has {audit.threshold}+ out-of-envelope denials in "
                f"{audit.window.days}d."
            )
        for line in audit.armed:
            lines.append(f"TRIGGER ARMED: {line}")
        for line in audit.faults:
            lines.append(f"AUDIT FAULT: {line}")

    _emit(payload, as_json=args.json, text="\n".join(lines))
    return 10 if (audit is not None and not audit.clean) else EXIT_OK


def cmd_declare(args: argparse.Namespace) -> int:
    """Declare an envelope. Validated against the registry before it is written."""
    registry, _ = _load(args)
    existing = _load_envelopes(args, registry)
    if existing.get(args.id) is not None:
        print(f"error: envelope {args.id} already exists", file=sys.stderr)
        return EXIT_ERROR

    capability = registry.capabilities.get(args.capability)
    if capability is None:
        print(f"error: unknown capability {args.capability}", file=sys.stderr)
        return EXIT_ERROR
    if not capability.envelope_bounded:
        print(
            f"refused: {capability.id} is not envelope-bounded. Declaring a bound for "
            "a capability the gate does not check is a record nobody reads",
            file=sys.stderr,
        )
        return EXIT_ERROR

    limits: dict[str, list[float]] = {}
    for spec in args.limit or ():
        key, sep, rng = str(spec).partition("=")
        low, colon, high = rng.partition(":")
        if not sep or not colon or not key.strip():
            print(f"error: --limit expects KEY=LOW:HIGH, got {spec!r}", file=sys.stderr)
            return EXIT_ERROR
        try:
            limits[key.strip()] = [float(low), float(high)]
        except ValueError:
            print(f"error: --limit {spec!r} bounds are not numbers", file=sys.stderr)
            return EXIT_ERROR

    issued_at = now_utc()
    try:
        ttl = parse_duration(args.ttl)
        candidate = Envelope(
            id=args.id,
            principal=args.principal,
            capability=args.capability,
            signed_by=args.signed_by,
            manifest_ref=args.manifest_ref,
            targets=tuple(args.target),
            limits=limits,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
        )
        EnvelopeRegister.for_registry(registry, envelopes=[*existing, candidate])
    except NeuraxisError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ERROR

    EnvelopeRegister.append_to_file(args.envelopes_file, candidate)
    _emit(
        candidate.to_dict(),
        as_json=args.json,
        text=(
            f"envelope {candidate.id} declared for {candidate.principal} on "
            f"{candidate.capability} until {candidate.expires_at.isoformat()}\n"
            f"  targets: {', '.join(candidate.targets)}\n"
            f"  limits: {', '.join(sorted(candidate.limits)) or 'none'}\n"
            f"  signed by {candidate.signed_by}, who is not {candidate.principal}"
        ),
    )
    return EXIT_OK


def cmd_waivers(args: argparse.Namespace) -> int:
    """Report the exception path: what is waived, by whom, until when.

    Exits 10 when an ILR-001-DR D-05 reversal trigger is armed. A trigger is
    not an error in the file — the records are well formed — it is a statement
    that the matrix is being held open by exception more than the ruling
    permits, and it should fail a pipeline that checks it.
    """
    registry, _ = _load(args)
    waivers = _load_waivers(args, registry)
    at = now_utc()
    active_ids = {w.id for w in waivers.active(at)}
    triggers = waivers.triggers(at)

    payload = {
        "policy": {
            "non_compensable": sorted(registry.waiver_policy.non_compensable),
            "max_ttl": _window(registry.waiver_policy.max_ttl),
            "max_active": registry.waiver_policy.max_active,
            "max_renewals": registry.waiver_policy.max_renewals,
        },
        "waivers": [
            {**w.to_dict(), "active": w.id in active_ids} for w in waivers
        ],
        "active": sorted(active_ids),
        "triggers": list(triggers),
    }

    lines = [
        f"non-compensable: {', '.join(sorted(registry.waiver_policy.non_compensable)) or 'none'}"
        "  (no waiver path at any TTL)",
        f"bounds: max_ttl={_window(registry.waiver_policy.max_ttl)} "
        f"max_active={registry.waiver_policy.max_active} "
        f"max_renewals={registry.waiver_policy.max_renewals}",
        "",
    ]
    if not len(waivers):
        lines.append("No waivers on file. The gate is unconditional.")
    else:
        lines.append("ID                STATE     CONTROL  BANDS            EXPIRES")
        for w in waivers:
            state = "ACTIVE" if w.id in active_ids else (
                "PENDING" if at < w.issued_at else "EXPIRED"
            )
            lines.append(
                f"{w.id:<17} {state:<9} {w.control:<8} "
                f"{','.join(w.bands):<16} {w.expires_at.isoformat()}"
            )
            lines.append(
                f"    accountable: {w.accountable}   issued by: {w.issued_by}"
            )
            lines.append(f"    compensating: {w.compensating_control}")
            lines.append(f"    ratification: {w.ratification_ref}")
    for line in triggers:
        lines.append("")
        lines.append(f"TRIGGER ARMED: {line}")

    _emit(payload, as_json=args.json, text="\n".join(lines))
    return 10 if triggers else EXIT_OK


def cmd_waive(args: argparse.Namespace) -> int:
    """Issue a waiver. Validated against the whole register before it is written.

    Validation runs over the existing records plus this one, so a waiver that
    would breach the renewal depth or waive a non-compensable control is
    refused at issue rather than discovered at the next load — by which time
    someone is relying on it.
    """
    registry, _ = _load(args)
    existing = _load_waivers(args, registry)
    if existing.get(args.id) is not None:
        print(f"error: waiver {args.id} already exists", file=sys.stderr)
        return EXIT_ERROR

    issued_at = now_utc()
    try:
        ttl = parse_duration(args.ttl)
    except NeuraxisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    candidate = Waiver(
        id=args.id.strip(),
        control=args.control.strip(),
        bands=tuple(b.strip() for b in args.band),
        accountable=args.accountable.strip(),
        issued_by=args.issued_by.strip(),
        compensating_control=args.compensating.strip(),
        ratification_ref=args.ratification_ref.strip(),
        issued_at=issued_at,
        expires_at=issued_at + ttl,
        renews=args.renews.strip() if args.renews else None,
    )
    try:
        WaiverRegister.for_registry(registry, waivers=[*existing, candidate])
    except NeuraxisError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ERROR

    WaiverRegister.append_to_file(args.waivers, candidate)
    payload = candidate.to_dict()
    _emit(
        payload,
        as_json=args.json,
        text=(
            f"waiver {candidate.id} issued: {candidate.control} for "
            f"{', '.join(candidate.bands)} until {candidate.expires_at.isoformat()}\n"
            f"  accountable: {candidate.accountable}\n"
            f"  compensating: {candidate.compensating_control}\n"
            f"  it does not license {candidate.issued_by} or {candidate.accountable}"
        ),
    )
    return EXIT_OK


def cmd_contract(args: argparse.Namespace) -> int:
    """Emit the CLI contract as JSON.

    Non-Python clients assert their own tables against this instead of
    hard-coding a copy. Adding a Decision in Python then breaks their tests
    loudly, rather than producing an exit code they silently map to nothing —
    and "maps to nothing" in a governance gate means "not recognised as a
    block".
    """
    payload = {
        "version": __version__,
        "ok_exit": EXIT_OK,
        "error_exit": EXIT_ERROR,
        "decisions": {d.value: EXIT_BY_DECISION[d] for d in Decision},
        "permitting_decisions": [d.value for d in Decision if d.permits_action],
        "obligations": [o.value for o in Obligation],
        "risks": [r.value for r in Risk],
        "request_fields": {
            "required": list(REQUEST_REQUIRED_FIELDS),
            "optional": list(REQUEST_OPTIONAL_FIELDS),
        },
    }
    lines = [f"neuraxis contract v{payload['version']}", "  decisions:"]
    lines += [
        f"    {name:<20} exit {code}"
        + ("   <- the only permitting decision" if name in payload["permitting_decisions"] else "")
        for name, code in payload["decisions"].items()
    ]
    lines.append(f"    {'(error)':<20} exit {EXIT_ERROR}")
    _emit(payload, as_json=args.json, text="\n".join(lines))
    return EXIT_OK


def cmd_providers(args: argparse.Namespace) -> int:
    """Show provider coverage of the control set — a live dependency view."""
    registry = load_registry(args.registry)
    cover = coverage(registry.controls, log_path=args.task_log, gate_log_path=args.gate_log, lease_log_path=args.lease_log)
    instances = {p.name: p for p in providers_for(log_path=args.task_log, gate_log_path=args.gate_log, lease_log_path=args.lease_log)}

    rows = ["CONTROL  PROVIDER                        STATE     WINDOW"]
    payload: dict[str, Any] = {"controls": {}}
    for cid, names in cover.items():
        window = _window(registry.max_age_for(cid))
        if not names:
            rows.append(f"{cid:<8} {'(none)':<31} {'NO SOURCE':<9} {window}")
            payload["controls"][cid] = {"providers": [], "state": "no-source", "window": window}
            continue
        for name in names:
            provider = instances[name]
            state = "UNWIRED" if getattr(provider, "blocked_on", None) else "WIRED"
            note = getattr(provider, "blocked_on", "")
            rows.append(f"{cid:<8} {name:<31} {state:<9} {window}")
            if note:
                rows.append(f"{'':<8} {'':<31} blocked on: {note}")
            payload["controls"][cid] = {
                "providers": names, "state": state.lower(),
                "window": window, "blocked_on": note or None,
            }

    wired = sum(1 for c in payload["controls"].values() if c["state"] == "wired")
    payload["wired"] = wired
    payload["total"] = len(cover)
    rows.append("")
    rows.append(f"{wired} of {len(cover)} controls have a wired provider.")
    _emit(payload, as_json=args.json, text="\n".join(rows))
    return EXIT_OK


def cmd_assure(args: argparse.Namespace) -> int:
    """Run providers for controls that are due, record results, report band state.

    Exit is non-zero if any provider that was expected to attest did not. An
    UNWIRED control is reported but does not by itself fail the run, since it
    is a known gap rather than a regression.
    """
    registry, store = _load(args)
    waivers = _load_waivers(args, registry)
    resolver = BandResolver(registry, store, waivers)
    before = set(resolver.attained_bands())

    selected = providers_for(args.control, log_path=args.task_log, gate_log_path=args.gate_log, lease_log_path=args.lease_log)
    if not selected:
        print(f"error: no providers for {args.control or 'any control'}", file=sys.stderr)
        return EXIT_ERROR

    runs = []
    for provider in selected:
        if not args.force and store.holds(provider.control, registry.max_age_for(provider.control)):
            continue
        run = run_provider(provider)
        store.append_to_file(args.attestations, run.to_attestation())
        runs.append(run)

    after = set(BandResolver(registry, store, waivers).attained_bands())
    opened, closed = sorted(after - before), sorted(before - after)
    failures = [r for r in runs if r.result.outcome is ProviderOutcome.FAIL]
    unwired = [r for r in runs if r.result.outcome is ProviderOutcome.UNWIRED]

    payload = {
        "ran": [r.to_dict() for r in runs],
        "skipped_current": len(selected) - len(runs),
        "failed": [r.control for r in failures],
        "unwired": [r.control for r in unwired],
        "bands_opened": opened,
        "bands_closed": closed,
        "attained": sorted(after),
    }
    lines = [
        f"ran {len(runs)} provider(s); {len(selected) - len(runs)} skipped (still current)",
        f"  passed:  {len(runs) - len(failures) - len(unwired)}",
        f"  failed:  {len(failures)}" + (f"  {[r.control for r in failures]}" if failures else ""),
        f"  unwired: {len(unwired)}" + (f"  {[r.control for r in unwired]}" if unwired else ""),
    ]
    for run in failures:
        lines.append(f"  FAIL {run.control} ({run.provider}): {run.result.detail}")
    if closed:
        lines.append(f"  BANDS CLOSED: {', '.join(closed)}")
    if opened:
        lines.append(f"  bands opened: {', '.join(opened)}")
    lines.append(f"  attained: {', '.join(sorted(after)) or 'none'}")
    _emit(payload, as_json=args.json, text="\n".join(lines))

    return EXIT_BY_DECISION[Decision.DENY] if failures or closed else EXIT_OK


# ---- parser ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neuraxis",
        description="BST Neuraxis governance gate (ILR-001). Capability is licensed by attestation.",
    )
    parser.add_argument("--version", action="version", version=f"neuraxis {__version__}")
    parser.add_argument("--registry", default=None, help="path to neuraxis.yaml (default: bundled)")
    parser.add_argument("--attestations", default=DEFAULT_ATTESTATIONS, help="attestation JSONL path")
    parser.add_argument("--json", action="store_true", help="emit JSON (the machine contract)")
    parser.add_argument(
        "--task-log", default="task-log.jsonl",
        help="task log consumed by the verifier-independence provider (GV-04)",
    )
    parser.add_argument(
        "--gate-log", default="gate-log.jsonl", dest="gate_log",
        help="BADF gate log consumed by the ratification provider (GV-07)",
    )
    parser.add_argument(
        "--evidence-sink", default=None, dest="evidence_sink",
        help="append gate decisions and obligation discharges here (JSONL)",
    )
    parser.add_argument(
        "--lease-log", default="lease-log.jsonl", dest="lease_log",
        help="L0 lease log consumed by the authority and containment providers (GV-02, GV-06)",
    )
    parser.add_argument(
        "--waivers", default="waivers.jsonl", dest="waivers",
        help="recorded, expiring exceptions to the gate (JSONL); absent means none",
    )
    parser.add_argument(
        "--envelopes", default="envelopes.jsonl", dest="envelopes_file",
        help="declared bounds for envelope-bounded capabilities (JSONL); absent means none",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate registry integrity")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser(
        "drift", help="is the kernel registry on disk the ratified one? (KBS-001 K-09)"
    )
    p.add_argument("--expect", default=None, help="the ratified sha256 to compare against")
    p.add_argument(
        "--expect-file", default=None, dest="expect_file",
        help="a REGISTRY-DIGEST.txt from the release you believe you are running",
    )
    p.set_defaults(func=cmd_drift)

    p = sub.add_parser("status", help="band attainment against current attestations")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("gate", help="evaluate an authority request")
    p.add_argument("request", nargs="?", default="", help="'-' to read a JSON request from stdin")
    p.add_argument("--capability", help="IL-nn")
    p.add_argument("--identity")
    p.add_argument("--role")
    p.add_argument("--intent")
    p.add_argument("--scope", default="default")
    p.add_argument("--risk", default="LOW", choices=[r.value for r in Risk])
    p.add_argument("--verifier", default=None)
    p.add_argument("--rollback-tested", action="store_true", dest="rollback_tested")
    p.add_argument("--ratification-ref", default=None, dest="ratification_ref")
    p.add_argument(
        "--envelope-ref", default=None, dest="envelope_ref",
        help="the declared bound this adjustment claims to sit inside (IL-13a)",
    )
    p.add_argument(
        "--adjust", action="append", default=None, metavar="KEY=VALUE",
        help="a parameter this request proposes to change; repeat for several",
    )
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("attest", help="record a governance control attestation")
    p.add_argument("--control", required=True, help="GV-nn")
    p.add_argument("--result", choices=["pass", "fail"], default=None)
    p.add_argument("--issuer", default=None)
    p.add_argument("--evidence-ref", dest="evidence_ref", default=None)
    p.add_argument(
        "--from-provider", dest="from_provider", default=None,
        help="run this provider and record its result instead of asserting one by hand",
    )
    p.set_defaults(func=cmd_attest)

    p = sub.add_parser("discharge", help="record that an obligation of a verdict was met")
    p.add_argument("--verdict", required=True, help="verdict_id from the gate")
    p.add_argument("--obligation", required=True)
    p.add_argument("--by", required=True, help="identity discharging it; may not be the performer")
    p.add_argument("--evidence-ref", required=True, dest="evidence_ref")
    p.set_defaults(func=cmd_discharge)

    p = sub.add_parser("obligations", help="what the gate's ALLOWs owe, and what has been paid")
    p.add_argument("--grace", default=None, help="ignore obligations newer than this, e.g. 30m")
    p.set_defaults(func=cmd_obligations)

    p = sub.add_parser("envelopes", help="declared bounds for envelope-bounded capabilities")
    p.add_argument(
        "--audit", action="store_true",
        help="count out-of-envelope denials per envelope from the evidence sink",
    )
    p.set_defaults(func=cmd_envelopes)

    p = sub.add_parser("declare", help="declare an envelope for an envelope-bounded capability")
    p.add_argument("--id", required=True, help="stable id; the audit handle for this bound")
    p.add_argument("--principal", required=True, help="the component this envelope bounds")
    p.add_argument("--capability", required=True, help="the envelope-bounded IL-nn")
    p.add_argument(
        "--signed-by", required=True, dest="signed_by",
        help="who declares it; may not be the principal it bounds",
    )
    p.add_argument(
        "--manifest-ref", required=True, dest="manifest_ref",
        help="reference to the signed mission manifest this bound comes from",
    )
    p.add_argument(
        "--target", required=True, action="append",
        help="a write-target prefix the principal may touch; repeat for several",
    )
    p.add_argument(
        "--limit", action="append", default=None, metavar="KEY=LOW:HIGH",
        help="a numeric interval a parameter may move within; repeat for several",
    )
    p.add_argument("--ttl", required=True, help="hard expiry as a duration, e.g. '30d'")
    p.set_defaults(func=cmd_declare)

    p = sub.add_parser("waivers", help="the exception path: what is waived, by whom, until when")
    p.set_defaults(func=cmd_waivers)

    p = sub.add_parser("waive", help="issue a recorded, expiring waiver")
    p.add_argument("--id", required=True, help="stable id; the audit handle for this waiver")
    p.add_argument("--control", required=True, help="the GV control waived")
    p.add_argument(
        "--band", required=True, action="append",
        help="band this waiver licenses; repeat for several. No default: an "
             "unscoped waiver is a waiver-by-default",
    )
    p.add_argument("--accountable", required=True, help="named person answerable for the gap")
    p.add_argument("--issued-by", required=True, dest="issued_by", help="issuing principal")
    p.add_argument(
        "--compensating", required=True,
        help="the control standing in for the waived one, in one line",
    )
    p.add_argument(
        "--ratification-ref", required=True, dest="ratification_ref",
        help="reference to the human ratification of this exception",
    )
    p.add_argument("--ttl", required=True, help="hard expiry as a duration, e.g. '30d'")
    p.add_argument("--renews", default=None, help="id of the waiver this one replaces")
    p.set_defaults(func=cmd_waive)

    p = sub.add_parser("contract", help="machine-readable CLI contract for non-Python clients")
    p.set_defaults(func=cmd_contract)

    p = sub.add_parser("providers", help="provider coverage of the control set")
    p.set_defaults(func=cmd_providers)

    p = sub.add_parser("assure", help="run due providers, record results, report band changes")
    p.add_argument("--control", default=None, help="limit to one GV-nn")
    p.add_argument("--force", action="store_true", help="re-run providers whose control is current")
    p.set_defaults(func=cmd_assure)

    p = sub.add_parser("score", help="effective-intelligence scorecard for a band")
    p.add_argument("--band", default=None)
    p.add_argument("--exam-pass-rate", type=float, default=0.0)
    p.add_argument("--lesson-yield", type=float, default=0.0)
    p.add_argument("--retrieval-precision", type=float, default=0.0)
    p.add_argument("--tasks-completed", type=int, default=0)
    p.add_argument("--tasks-attempted", type=int, default=0)
    p.add_argument("--verification-coverage", type=float, default=0.0)
    p.add_argument("--performer-is-verifier", action="store_true")
    p.set_defaults(func=cmd_score)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except NeuraxisError as exc:
        # Registry and attestation faults are errors, never silent allows.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
