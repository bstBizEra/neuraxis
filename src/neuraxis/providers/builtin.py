"""Built-in providers.

One is real. Nine are declared UNWIRED against named blockers, which is the
honest representation of where the T-queue actually stands — and it means
`neuraxis assure` refuses to attest those controls rather than skipping them
quietly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .base import Provider, ProviderResult, UnwiredProvider


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
        if not path.is_file():
            raise FileNotFoundError(f"task log not found at {path}")
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
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


# --- Controls with no source yet -------------------------------------------
# Each names its blocker so `neuraxis providers` reads as a live dependency view.

UNWIRED = (
    ("GV-01", "kbs-001/probe", "KBS-001 T1 — kernel boundary probe"),
    ("GV-02", "l0/lease-audit", "L0 enforcement layer — lease issuance log"),
    ("GV-03", "kbs-001/sink-worm", "KBS-001 T1 — WORM-backed evidence sink"),
    ("GV-05", "nx/rollback-drill", "neuraxis v0.4 — rollback drill runner"),
    ("GV-06", "l0/scope-budget", "L0 enforcement layer — scope and budget ceilings"),
    ("GV-07", "badf/gate-log", "BADF gate log export"),
    ("GV-08", "kbs-001/external-probe", "KBS-001 T1 — external assurance org"),
    ("GV-09", "nx/lesson-provenance", "neuraxis v0.4 — lesson provenance binding"),
    ("GV-10", "nx/killswitch-drill", "KBS-001 E-13 — kill switch"),
)


def builtin_providers(**config: Any) -> list[Provider]:
    """Every provider shipped with the package, real and unwired alike."""
    providers: list[Provider] = [
        VerifierIndependenceProvider(**{k: v for k, v in config.items() if k == "log_path"})
    ]
    providers.extend(
        UnwiredProvider(control=control, name=name, blocked_on=blocked_on)
        for control, name, blocked_on in UNWIRED
    )
    return providers
