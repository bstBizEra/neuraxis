"""Evidence records — the feedback edge from the gate back to the audits.

Until v0.7 the gate was write-only. It issued verdicts and nothing recorded
them, so the obligations attached to an ALLOW could not be audited: no later
cycle could observe that an ALLOW had even been issued, let alone that what it
owed went unpaid. `EMIT_EVIDENCE`, `BOUNDED_SCOPE` and `PROVENANCE_BINDING`
were labels on a verdict rather than controls.

This module closes that edge. Every evaluation appends an `EvidenceRecord`
naming the verdict and the obligations it owes; discharging an obligation
appends a `DischargeRecord` joined by `verdict_id`. The two together are what
an audit needs to say "this ALLOW was issued and never paid for".

**What this does not do.** The sink is an ordinary append-only file that the
audited party can also write. It creates the record stream GV-03 is meant to
protect; it does not protect it, and it does not attest GV-03. Omission stays
undetectable until the WORM sink from KBS-001 T1 exists. Building the stream
first is deliberate — when T1 lands there is something for it to make
tamper-evident, rather than a sink with nothing in it.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .envelope import OUT_OF_ENVELOPE
from .errors import NeuraxisError
from .model import AuthorityRequest, Obligation, Verdict, now_utc

EVIDENCE = "evidence"
DISCHARGE = "discharge"


class EvidenceError(NeuraxisError):
    """The sink could not be written or read.

    Raised rather than swallowed: an ALLOW that cannot be recorded must not be
    issued, so callers convert this into a denial.
    """


def new_verdict_id() -> str:
    """A random id, not a content hash.

    A content hash would collide for two genuinely distinct evaluations of the
    same request in the same instant, and merging those into one record would
    hide one of them.
    """
    return secrets.token_hex(8)


@dataclass(frozen=True)
class EvidenceRecord:
    """One gate decision, and what it obliges the caller to do."""

    verdict_id: str
    at: datetime
    decision: str
    capability: str
    band: str | None
    identity: str
    performer: str
    role: str
    scope: str
    intent: str
    obligations: tuple[str, ...]
    reasons: tuple[str, ...]
    # ILR-001-DR D-01. Carried so an adjustment is auditable against the bound
    # it claimed, and so out-of-envelope denials can be counted per envelope
    # without parsing prose.
    envelope_ref: str | None = None
    adjustments: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def build(
        cls, request: AuthorityRequest, verdict: Verdict, *, verdict_id: str | None = None
    ) -> "EvidenceRecord":
        return cls(
            verdict_id=verdict_id or new_verdict_id(),
            at=verdict.evaluated_at,
            decision=verdict.decision.value,
            capability=verdict.capability,
            band=verdict.band,
            identity=request.identity,
            performer=request.effective_performer,
            role=request.role,
            scope=request.scope,
            intent=request.intent,
            obligations=tuple(o.value for o in verdict.obligations),
            reasons=tuple(verdict.reasons),
            envelope_ref=request.envelope_ref,
            adjustments=dict(request.adjustments),
        )

    @property
    def permitted(self) -> bool:
        return self.decision == "ALLOW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": EVIDENCE,
            "verdict_id": self.verdict_id,
            "at": self.at.isoformat(),
            "decision": self.decision,
            "capability": self.capability,
            "band": self.band,
            "identity": self.identity,
            "performer": self.performer,
            "role": self.role,
            "scope": self.scope,
            "intent": self.intent,
            "obligations": list(self.obligations),
            "reasons": list(self.reasons),
            "envelope_ref": self.envelope_ref,
            "adjustments": dict(self.adjustments),
        }


@dataclass(frozen=True)
class DischargeRecord:
    """A claim that one obligation of one verdict was met."""

    verdict_id: str
    obligation: str
    at: datetime
    by: str
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": DISCHARGE,
            "verdict_id": self.verdict_id,
            "obligation": self.obligation,
            "at": self.at.isoformat(),
            "by": self.by,
            "evidence_ref": self.evidence_ref,
        }


class EvidenceSink:
    """Append-only JSONL writer and reader for the two record kinds."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: EvidenceRecord | DischargeRecord) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        except OSError as exc:
            raise EvidenceError(f"could not append to evidence sink {self.path}: {exc}") from exc

    def read(self) -> Iterator[dict[str, Any]]:
        """Yield raw records. Absent sink yields nothing; malformed raises.

        `split("\\n")` rather than `splitlines()`, for the same reason as the
        other readers: splitlines() also breaks on separators that are legal
        inside a JSON string and invisible to a line-based auditor.
        """
        if not self.path.is_file():
            return
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise EvidenceError(f"could not read evidence sink {self.path}: {exc}") from exc
        for lineno, line in enumerate(text.split("\n"), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"{self.path}:{lineno}: {exc}") from exc
            if not isinstance(record, dict):
                raise EvidenceError(f"{self.path}:{lineno}: record is not an object")
            yield record


@dataclass(frozen=True)
class OutstandingObligation:
    """An obligation an ALLOW owes that no discharge has paid."""

    verdict_id: str
    obligation: str
    capability: str
    performer: str
    at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "obligation": self.obligation,
            "capability": self.capability,
            "performer": self.performer,
            "at": self.at.isoformat(),
        }


@dataclass(frozen=True)
class ObligationAudit:
    """What the sink says about obligations owed and paid."""

    allowed: int
    owed: int
    discharged: int
    outstanding: tuple[OutstandingObligation, ...]
    faults: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.outstanding and not self.faults

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "owed": self.owed,
            "discharged": self.discharged,
            "outstanding": [o.to_dict() for o in self.outstanding],
            "faults": list(self.faults),
            "clean": self.clean,
        }


@dataclass(frozen=True)
class EnvelopeAudit:
    """Out-of-envelope denials over a window, per envelope (ILR-001-DR D-01).

    The register's reversal trigger is "two or more out-of-envelope denials
    overridden by waiver within any 90-day window", and the second half of that
    cannot be implemented faithfully: Neuraxis waives *controls*, not
    individual denials, and no per-request override path exists -- deliberately,
    since one would be exactly the loophole D-01 warns the split could become.

    So what is counted is the half that is real and still diagnostic: repeated
    out-of-envelope denials against the same envelope. Two or more means either
    the envelope is mis-specified or the split is being leaned on, which is the
    condition the trigger was written to surface. It is reported as an
    observation about the envelope, never as an authorisation to widen it.
    """

    window: timedelta
    denials: Mapping[str, int]
    armed: tuple[str, ...]
    #: The count at which a trigger arms. Carried because for a reversal
    #: trigger the threshold *is* the finding: a clean report produced by a
    #: raised threshold must not be indistinguishable from a clean sink.
    threshold: int = 2
    #: Records the audit could not read. A sink the audited party can also
    #: write can be made unreadable by appending one malformed line, so a
    #: fault is reported as not-clean rather than raised past the caller.
    faults: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.armed and not self.faults

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_days": self.window.days,
            "threshold": self.threshold,
            "denials": dict(sorted(self.denials.items())),
            "armed": list(self.armed),
            "faults": list(self.faults),
            "clean": self.clean,
        }


def audit_envelopes(
    records: Iterable[dict[str, Any]],
    *,
    window: timedelta = timedelta(days=90),
    threshold: int = 2,
    at: datetime | None = None,
) -> EnvelopeAudit:
    """Count out-of-envelope denials per envelope inside `window`."""
    at = at or now_utc()
    cutoff = at - window
    counts: dict[str, int] = {}
    faults: list[str] = []
    for row in _tolerant(records, faults):
        if not isinstance(row, dict) or row.get("record") != EVIDENCE:
            continue
        if row.get("decision") == "ALLOW":
            continue
        ref = row.get("envelope_ref")
        if not isinstance(ref, str) or not ref.strip():
            continue
        reasons = row.get("reasons")
        if not isinstance(reasons, list):
            continue
        if not any(isinstance(r, str) and r.startswith(OUT_OF_ENVELOPE) for r in reasons):
            continue
        try:
            when = datetime.fromisoformat(str(row.get("at")))
        except (TypeError, ValueError):
            when = None
        if when is None or when.tzinfo is None:
            # An unparseable or naive timestamp is counted, not dropped. The
            # window is a reporting convenience; silently discarding a denial
            # because its clock is unreadable would make the trigger easier to
            # avoid than to satisfy, and dropping the offset is one edit.
            counts[ref.strip()] = counts.get(ref.strip(), 0) + 1
            continue
        if when < cutoff:
            continue
        counts[ref.strip()] = counts.get(ref.strip(), 0) + 1

    armed = tuple(
        f"D-01: {ref} has {n} out-of-envelope denials in {window.days}d "
        f"(threshold {threshold}). Either the envelope is mis-specified or the "
        "IL-13a split is being leaned on; re-declare the bound deliberately "
        "rather than widening it under pressure"
        for ref, n in sorted(counts.items())
        if n >= threshold
    )
    return EnvelopeAudit(
        window=window,
        denials=counts,
        armed=armed,
        threshold=threshold,
        faults=tuple(faults),
    )


def _tolerant(records: Iterable[dict[str, Any]], faults: list[str]) -> Iterator[dict[str, Any]]:
    """Yield records, converting a reader error into a fault rather than a raise.

    `EvidenceSink.read()` raises on the first malformed line, which is right for
    a loader and wrong for an audit: the sink is a file the audited party can
    also write, so one appended `{` would otherwise abort every subsequent audit
    run instead of reporting an armed trigger.
    """
    iterator = iter(records)
    while True:
        try:
            yield next(iterator)
        except StopIteration:
            return
        except NeuraxisError as exc:
            faults.append(f"the evidence sink could not be read past this point: {exc}")
            return


def audit_obligations(
    records: Iterable[dict[str, Any]], *, grace: Any = None, at: datetime | None = None
) -> ObligationAudit:
    """Join discharges to the ALLOWs that owe them.

    Only an ALLOW owes anything — a DENY obliges nobody to do anything, so
    counting its obligations would inflate the debt with duties that were never
    incurred.

    `grace` (a timedelta) excludes obligations too recent to be overdue; without
    it every in-flight ALLOW reads as outstanding.
    """
    at = at or now_utc()
    verdicts: dict[str, dict[str, Any]] = {}
    discharges: list[dict[str, Any]] = []
    faults: list[str] = []

    for record in records:
        kind = str(record.get("record", "")).strip().lower()
        if kind == EVIDENCE:
            vid = record.get("verdict_id")
            if not vid:
                faults.append("evidence record with no verdict_id")
                continue
            if vid in verdicts:
                # Two records under one id means one of them is describing a
                # decision that is not its own.
                faults.append(f"duplicate verdict_id {vid}")
                continue
            verdicts[vid] = record
        elif kind == DISCHARGE:
            discharges.append(record)
        else:
            faults.append(f"record of unrecognised kind {kind or '<absent>'!r}")

    paid: set[tuple[str, str]] = set()
    for discharge in discharges:
        vid = discharge.get("verdict_id")
        obligation = discharge.get("obligation")
        if not vid or not obligation:
            faults.append("discharge record missing verdict_id or obligation")
            continue
        verdict = verdicts.get(vid)
        if verdict is None:
            # A discharge for a verdict that was never issued is either a
            # forged payment or a lost record; both are faults.
            faults.append(f"discharge {obligation} references unknown verdict {vid}")
            continue
        if obligation not in (verdict.get("obligations") or []):
            faults.append(f"discharge {obligation} not owed by verdict {vid}")
            continue
        by = (discharge.get("by") or "").strip().casefold()
        performer = (verdict.get("performer") or "").strip().casefold()
        if by and performer and by == performer:
            # Self-discharge is the NX-INV-2 failure applied to obligations.
            faults.append(f"verdict {vid}: {obligation} discharged by the performer {by!r}")
            continue
        paid.add((vid, obligation))

    owed = 0
    outstanding: list[OutstandingObligation] = []
    allowed = 0
    for vid, verdict in verdicts.items():
        if verdict.get("decision") != "ALLOW":
            continue
        allowed += 1
        try:
            issued = datetime.fromisoformat(str(verdict.get("at")))
        except (TypeError, ValueError):
            faults.append(f"verdict {vid}: unparseable timestamp {verdict.get('at')!r}")
            continue
        if issued.tzinfo is None:
            faults.append(f"verdict {vid}: timestamp has no timezone offset")
            continue
        for obligation in verdict.get("obligations") or []:
            owed += 1
            if (vid, obligation) in paid:
                continue
            if grace is not None and (at - issued) < grace:
                continue
            outstanding.append(
                OutstandingObligation(
                    verdict_id=vid,
                    obligation=obligation,
                    capability=str(verdict.get("capability", "")),
                    performer=str(verdict.get("performer", "")),
                    at=issued,
                )
            )

    return ObligationAudit(
        allowed=allowed,
        owed=owed,
        discharged=len(paid),
        outstanding=tuple(outstanding),
        faults=tuple(dict.fromkeys(faults)),
    )


def record_decision(
    sink: EvidenceSink | None, request: AuthorityRequest, verdict: Verdict
) -> tuple[Verdict, EvidenceRecord | None]:
    """Append the decision, and deny an ALLOW that could not be recorded.

    An ALLOW carrying EMIT_EVIDENCE that cannot be written is a permission
    granted with no trace, which is the condition GV-03 exists to rule out. So
    the write failure is converted into a denial rather than logged and
    ignored — the caller is refused, not silently unaudited.
    """
    if sink is None:
        return verdict, None

    record = EvidenceRecord.build(request, verdict)
    try:
        sink.append(record)
    except EvidenceError as exc:
        if verdict.permits_action and Obligation.EMIT_EVIDENCE in verdict.obligations:
            from .model import Decision  # local import keeps the module import-light

            return (
                Verdict(
                    decision=Decision.DENY,
                    capability=verdict.capability,
                    band=verdict.band,
                    reasons=(
                        f"the decision could not be recorded: {exc}",
                        "an ALLOW owing EMIT_EVIDENCE that leaves no trace is not issued",
                    ),
                ),
                None,
            )
        # A block that could not be recorded is still a block; nothing was
        # permitted, so there is no untraced action to worry about.
        return verdict, None
    return verdict, record
