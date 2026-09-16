"""Built-in providers.

Four are real. Six are declared UNWIRED against named blockers, which is the
honest representation of where the T-queue actually stands — and it means
`neuraxis assure` refuses to attest those controls rather than skipping them
quietly.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .base import Provider, ProviderResult, UnwiredProvider


def read_jsonl(path: Path, *, what: str) -> Iterable[dict[str, Any]]:
    """Read a JSONL evidence file.

    `utf-8-sig` because PowerShell writes a BOM by default and a BOM on line 1
    would otherwise make the whole file unreadable — which fails closed, but
    for an encoding reason rather than the reason the check is about.
    """
    if not path.is_file():
        raise FileNotFoundError(f"{what} not found at {path}")
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").split("\n"), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{lineno}: record is not an object")
        yield record


def parse_ts(value: Any, *, field: str, where: str) -> datetime:
    """Parse a required ISO-8601 timestamp, rejecting naive values.

    Ordering is what three of the five GV-07 checks turn on, and ordering
    across mixed or absent offsets is not decidable — so a naive timestamp is
    a breach rather than something to coerce.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: {field} missing")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{where}: {field} is not ISO-8601 ({value!r})") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{where}: {field} has no timezone offset ({value!r})")
    return parsed


class VerifierIndependenceProvider(Provider):
    """GV-04 — audits a task log for performer/verifier independence (NX-INV-2).

    Source: a JSONL task log, one record per completed task, each carrying
    `task_id`, `performer` and `verifier`. Any record where verifier is absent
    or equals performer breaks independence for the whole sample: this is not a
    ratio to optimise, it is a property that holds or does not.
    """

    control = "GV-04"
    name = "nx/verifier-independence"

    def __init__(self, log_path: str | Path = "task-log.jsonl", **config: Any) -> None:
        self.log_path = Path(log_path)
        super().__init__(log_path=str(log_path), **config)

    # ---- conformance ---------------------------------------------------

    def positive_control(self) -> bool:
        """The log must exist and parse. No log means the check is not live."""
        try:
            records = list(self._read(self.log_path))
        except Exception:  # noqa: BLE001
            return False
        return len(records) > 0

    def vacuity_probe(self) -> ProviderResult:
        """Audit a synthetic self-verified record. It must FAIL."""
        return self._audit(
            [{"task_id": "vacuity-probe", "performer": "agent-x", "verifier": "agent-x"}],
            evidence_ref="synthetic://vacuity-probe",
        )

    # ---- the check -----------------------------------------------------

    def check(self) -> ProviderResult:
        try:
            records = list(self._read(self.log_path))
        except Exception as exc:  # noqa: BLE001
            return ProviderResult.failed(f"task log unreadable: {exc}")
        return self._audit(records, evidence_ref=f"file://{self.log_path}")

    # ---- internals -----------------------------------------------------

    @staticmethod
    def _read(path: Path) -> Iterable[dict[str, Any]]:
        return read_jsonl(path, what="task log")

    @staticmethod
    def _audit(records: list[dict[str, Any]], *, evidence_ref: str) -> ProviderResult:
        breaches: list[str] = []
        for record in records:
            task = record.get("task_id", "<unidentified>")
            performer = record.get("performer")
            verifier = record.get("verifier")
            if not performer:
                breaches.append(f"{task}: no performer recorded")
            elif not verifier:
                breaches.append(f"{task}: no verifier recorded")
            elif verifier == performer:
                breaches.append(f"{task}: verifier equals performer ({performer})")

        if breaches:
            return ProviderResult.failed(
                f"{len(breaches)} of {len(records)} task(s) break verifier independence: "
                + "; ".join(breaches[:5]) + ("..." if len(breaches) > 5 else ""),
                evidence_ref=evidence_ref,
                breaches=len(breaches),
                sampled=len(records),
            )
        return ProviderResult.passed(
            evidence_ref,
            f"all {len(records)} sampled task(s) verified by an identity other than the performer",
            breaches=0,
            sampled=len(records),
        )


class GateLogRatificationProvider(Provider):
    """GV-07 — audits the BADF gate log for genuine human ratification.

    The control: *defined change classes require human authorization;
    automation may propose, never merge.* The record contract this reads is
    specified in docs/GV-07-gate-log-contract.md — the control states what must
    be true, the provider states what evidence would show it, and the export is
    built to match. The reverse order is how a check ends up measuring whatever
    the source happened to emit.

    Five breach classes, all fatal to the sample. Ratification is a property
    that holds or does not; a ratio would invite optimising it.
    """

    control = "GV-07"
    name = "badf/gate-log"

    def __init__(self, gate_log_path: str | Path = "gate-log.jsonl", **config: Any) -> None:
        self.gate_log_path = Path(gate_log_path)
        super().__init__(gate_log_path=str(gate_log_path), **config)

    # ---- conformance ---------------------------------------------------

    def positive_control(self) -> bool:
        """The log must exist, parse, and hold at least one record.

        An empty log is not "zero breaches" — it is no evidence, and a denial
        from a check that is not live proves nothing.
        """
        try:
            return len(list(read_jsonl(self.gate_log_path, what="gate log"))) > 0
        except Exception:  # noqa: BLE001
            return False

    def vacuity_probe(self) -> ProviderResult:
        """Audit a change whose proposer ratified it. Must FAIL."""
        return self._audit(
            [
                {
                    "change_id": "vacuity-probe",
                    "proposer": "agent-drafter",
                    "ratifier": "agent-drafter",
                    "ratifier_kind": "human",
                    "ratified_at": "2026-01-01T00:00:00+00:00",
                    "merged_at": "2026-01-01T00:05:00+00:00",
                }
            ],
            evidence_ref="synthetic://vacuity-probe",
        )

    # ---- the check -----------------------------------------------------

    def check(self) -> ProviderResult:
        try:
            records = list(read_jsonl(self.gate_log_path, what="gate log"))
        except Exception as exc:  # noqa: BLE001
            return ProviderResult.failed(f"gate log unreadable: {exc}")
        return self._audit(records, evidence_ref=f"file://{self.gate_log_path}")

    # ---- internals -----------------------------------------------------

    @staticmethod
    def _audit(records: list[dict[str, Any]], *, evidence_ref: str) -> ProviderResult:
        breaches: list[str] = []

        for record in records:
            change = record.get("change_id", "<unidentified>")
            proposer = record.get("proposer")
            ratifier = record.get("ratifier")
            kind = str(record.get("ratifier_kind", "")).strip().lower()

            if not proposer:
                breaches.append(f"{change}: no proposer recorded")
                continue
            if not ratifier:
                breaches.append(f"{change}: merged with no ratifier")
                continue
            if ratifier == proposer:
                breaches.append(f"{change}: self-ratified by {proposer}")
                continue
            if kind != "human":
                # "automation may propose; it may not merge" — a bot ratifier
                # satisfies the record and defeats the control.
                breaches.append(
                    f"{change}: ratified by {ratifier!r} of kind "
                    f"{kind or '<unspecified>'!r}, not human"
                )
                continue

            try:
                ratified = parse_ts(record.get("ratified_at"), field="ratified_at", where=change)
                merged = parse_ts(record.get("merged_at"), field="merged_at", where=change)
            except ValueError as exc:
                breaches.append(str(exc))
                continue

            if ratified >= merged:
                # The check worth building for: a gate that still runs but has
                # become a stamp on a completed act rather than an authorisation
                # of it. It looks green the whole way.
                #
                # `>=`, not `>`: ratification at the same instant as the merge
                # is not authorisation preceding the act, it is both emitted by
                # one automated step.
                breaches.append(
                    f"{change}: ratified at or after merge "
                    f"({ratified.isoformat()} >= {merged.isoformat()})"
                )
                continue

            proposed_raw = record.get("proposed_at")
            if "proposed_at" in record and not proposed_raw:
                # Present-but-falsy skipped the ordering check entirely, so ""
                # and 0 were a free pass while "garbage" was a breach. That is
                # the wrong way round.
                breaches.append(
                    f"{change}: proposed_at is present but empty ({proposed_raw!r})"
                )
                continue
            if proposed_raw:
                try:
                    proposed = parse_ts(proposed_raw, field="proposed_at", where=change)
                except ValueError as exc:
                    breaches.append(str(exc))
                    continue
                if ratified < proposed:
                    breaches.append(f"{change}: ratified before it was proposed")

        if breaches:
            return ProviderResult.failed(
                f"{len(breaches)} of {len(records)} gated change(s) lack genuine "
                f"human ratification: " + "; ".join(breaches[:5])
                + ("..." if len(breaches) > 5 else ""),
                evidence_ref=evidence_ref,
                breaches=len(breaches),
                sampled=len(records),
            )
        return ProviderResult.passed(
            evidence_ref,
            f"all {len(records)} gated change(s) ratified by a human other than the "
            "proposer, before the merge",
            breaches=0,
            sampled=len(records),
        )


from .lease import LeaseAuthorityProvider, LeaseContainmentProvider  # noqa: E402

# --- Controls with no source yet -------------------------------------------
# Each names its blocker so `neuraxis providers` reads as a live dependency view.

UNWIRED = (
    ("GV-01", "kbs-001/probe", "KBS-001 T1 — kernel boundary probe"),
    ("GV-03", "kbs-001/sink-worm", "KBS-001 T1 — WORM-backed evidence sink"),
    ("GV-05", "nx/rollback-drill", "neuraxis v0.4 — rollback drill runner"),
    ("GV-08", "kbs-001/external-probe", "KBS-001 T1 — external assurance org"),
    ("GV-09", "nx/lesson-provenance", "neuraxis v0.4 — lesson provenance binding"),
    ("GV-10", "nx/killswitch-drill", "KBS-001 E-13 — kill switch"),
)


def builtin_providers(**config: Any) -> list[Provider]:  # noqa: D401
    """Every provider shipped with the package, real and unwired alike."""
    providers: list[Provider] = [
        VerifierIndependenceProvider(**{k: v for k, v in config.items() if k == "log_path"}),
        GateLogRatificationProvider(
            **{k: v for k, v in config.items() if k == "gate_log_path"}
        ),
        LeaseAuthorityProvider(
            **{k: v for k, v in config.items() if k == "lease_log_path"}
        ),
        LeaseContainmentProvider(
            **{k: v for k, v in config.items() if k == "lease_log_path"}
        ),
    ]
    providers.extend(
        UnwiredProvider(control=control, name=name, blocked_on=blocked_on)
        for control, name, blocked_on in UNWIRED
    )
    return providers
