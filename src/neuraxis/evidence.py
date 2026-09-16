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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

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
