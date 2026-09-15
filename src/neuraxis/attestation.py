"""Attestation storage and freshness.

An attestation says a governance control held at a point in time. Neuraxis
treats absence, expiry, failure and future-dating identically: the control
does not hold. That symmetry is deliberate — the KBS-001 review found that
most assurance failures come from a broken check scoring as a pass.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping

from .errors import AttestationError
from .model import Attestation, now_utc


class AttestationStore:
    """In-memory store keyed by control id, retaining only the newest record.

    Newest-wins is the correct policy: a fresh FAIL must supersede an older
    PASS, which a max-of-passes policy would hide.
    """

    def __init__(self, attestations: Iterable[Attestation] = ()) -> None:
        self._records: dict[str, Attestation] = {}
        for att in attestations:
            self.record(att)

    def record(self, attestation: Attestation) -> None:
        existing = self._records.get(attestation.control)
        if existing is None or attestation.issued_at >= existing.issued_at:
            self._records[attestation.control] = attestation

    def get(self, control: str) -> Attestation | None:
        return self._records.get(control)

    def holds(self, control: str, max_age: timedelta, *, at: datetime | None = None) -> bool:
        record = self._records.get(control)
        if record is None:
            return False
        return record.is_current(max_age, at=at)

    def explain(self, control: str, max_age: timedelta, *, at: datetime | None = None) -> str:
        """Human-readable reason a control does not hold. Used in verdicts."""
        at = at or now_utc()
        record = self._records.get(control)
        if record is None:
            return f"{control}: no attestation on file"
        if not record.result:
            return f"{control}: last attestation FAILED at {record.issued_at.isoformat()} ({record.evidence_ref})"
        age = at - record.issued_at
        if age < timedelta(0):
            return f"{control}: attestation is future-dated ({record.issued_at.isoformat()}); rejected"
        if age > max_age:
            return f"{control}: attestation expired ({_humanise(age)} old, max {_humanise(max_age)})"
        return f"{control}: holds"

    def missing(
        self,
        controls: Iterable[str],
        max_age_for: Callable[[str], timedelta] | timedelta,
        *,
        at: datetime | None = None,
    ) -> tuple[str, ...]:
        """Controls that do not currently hold.

        `max_age_for` is normally `Registry.max_age_for`, so each control is
        judged against its own window. A bare timedelta is accepted for callers
        that genuinely apply one window to everything.
        """
        resolve = max_age_for if callable(max_age_for) else (lambda _c: max_age_for)
        return tuple(c for c in controls if not self.holds(c, resolve(c), at=at))

    def __iter__(self) -> Iterator[Attestation]:
        return iter(sorted(self._records.values(), key=lambda a: a.control))

    def __len__(self) -> int:
        return len(self._records)

    # ---- persistence ---------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "AttestationStore":
        """Load attestations from a JSON lines file.

        A malformed line raises rather than being skipped: silently dropping a
        record could drop a FAIL and leave a band open.

        Read as utf-8-sig so a BOM is stripped. PowerShell writes one by
        default, and a BOM on line 1 would otherwise make the whole file
        unreadable — which fails closed, but for the wrong reason.
        """
        path = Path(path)
        if not path.is_file():
            return cls()
        store = cls()
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
                store.record(
                    Attestation(
                        control=payload["control"],
                        result=bool(payload["result"]),
                        issued_at=datetime.fromisoformat(payload["issued_at"]),
                        issuer=payload["issuer"],
                        evidence_ref=payload["evidence_ref"],
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise AttestationError(f"{path}:{lineno}: malformed attestation: {exc}") from exc
        return store

    def append_to_file(self, path: str | Path, attestation: Attestation) -> None:
        """Append one record. The file is a local mirror, not the sink of record.

        Under KBS-001 the authoritative evidence sink is WORM-backed; this file
        is an operator convenience and must not be treated as the audit trail.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "control": attestation.control,
            "result": attestation.result,
            "issued_at": attestation.issued_at.isoformat(),
            "issuer": attestation.issuer,
            "evidence_ref": attestation.evidence_ref,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self.record(attestation)

    def snapshot(
        self,
        max_age_for: Callable[[str], timedelta] | timedelta,
        *,
        at: datetime | None = None,
    ) -> Mapping[str, bool]:
        at = at or now_utc()
        resolve = max_age_for if callable(max_age_for) else (lambda _c: max_age_for)
        return {
            control: record.is_current(resolve(control), at=at)
            for control, record in self._records.items()
        }


def _humanise(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"
