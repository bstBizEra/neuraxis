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
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .attestation import AttestationStore
from .errors import NeuraxisError
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
from .registry import load_registry
from .resolver import BandResolver
from .scorecard import measure

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


def _emit(payload: dict[str, Any], *, as_json: bool, text: str | None = None) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif text is not None:
        print(text)


# ---- commands ----------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
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
        "warnings": (
            [f"band {b} is granted to no role" for b in ungranted]
            + [f"capability {c} has no band" for c in orphans]
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
    lines += [f"  WARNING: {w}" for w in payload["warnings"]]
    lines.append("  registry valid")
    _emit(payload, as_json=args.json, text="\n".join(lines))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    resolver = BandResolver(registry, store)
    statuses = resolver.all_statuses()

    payload = {
        "attestations_on_file": len(store),
        "bands": {bid: st.to_dict() for bid, st in statuses.items()},
        "attained": [bid for bid, st in statuses.items() if st.attained],
    }

    rows = ["BAND        STATUS        DETAIL"]
    for bid, st in statuses.items():
        mark = "ATTAINED" if st.attained else "BLOCKED"
        detail = st.reasons[0] if st.reasons else ""
        rows.append(f"{bid:<11} {mark:<13} {detail}")
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
    gate = GovernanceGate(registry, store)

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
        )

    verdict = gate.evaluate(request)
    if args.json:
        print(verdict.to_json())
    else:
        print(f"{verdict.decision.value} {verdict.capability} ({verdict.band or 'no band'})")
        for reason in verdict.reasons:
            print(f"  - {reason}")
        if verdict.obligations:
            print(f"  obligations: {', '.join(o.value for o in verdict.obligations)}")
    return EXIT_BY_DECISION[verdict.decision]


def cmd_attest(args: argparse.Namespace) -> int:
    registry, store = _load(args)
    if args.control not in registry.controls:
        print(f"error: unknown control {args.control}", file=sys.stderr)
        return EXIT_ERROR

    if args.from_provider:
        try:
            provider = get_provider(args.from_provider, log_path=args.task_log, gate_log_path=args.gate_log)
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
    resolver = BandResolver(registry, store)
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
    cover = coverage(registry.controls, log_path=args.task_log, gate_log_path=args.gate_log)
    instances = {p.name: p for p in providers_for(log_path=args.task_log, gate_log_path=args.gate_log)}

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
    resolver = BandResolver(registry, store)
    before = set(resolver.attained_bands())

    selected = providers_for(args.control, log_path=args.task_log, gate_log_path=args.gate_log)
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

    after = set(BandResolver(registry, store).attained_bands())
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
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate registry integrity")
    p.set_defaults(func=cmd_validate)

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
