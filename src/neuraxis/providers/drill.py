"""GV-05 reversibility — `nx/rollback-drill`.

GV-05 says a change can be reversed. The only evidence for that is a drill:
somebody mutated something real, rolled it back, and checked that what came
back is what was there before. Everything else is a plan to be reversible.

Which is why this provider is about **the drill that proves nothing**. The
breach worth building for is not a drill that failed — a failed drill is
useful, it tells you the rollback does not work and this control denies on it.
It is the drill that *passes* while measuring nothing:

  * nothing was mutated, so the rollback restored a system already in its
    baseline state, and
  * the restoration was declared rather than compared, so "restored" means the
    command exited zero.

Both look green. Both survive review. Both are the 30-day drill quietly
becoming the thing you run to keep the control open — which is exactly what
the README warns a long window invites: *"a stubbed drill is a vacuous check
wearing a different hat."* This provider is the hat check.

Like the lease and gate-log providers, it recomputes from raw records rather
than trusting a summary the performer emits about itself. A drill record
saying `"outcome": "restored"` is the claim under audit, not the audit.

Record contract: docs/GV-05-drill-log-contract.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from ..model import normalise_principal, now_utc
from .base import Provider, ProviderResult
from .builtin import parse_ts, read_jsonl

#: The oldest a drill may be and still attest the control, as a constant in
#: code rather than a setting, for ADR-0006's reason: a bound that exists to
#: constrain the evidence cannot be set by whoever supplies the evidence.
#:
#: It mirrors GV-05's registry window because they are the same claim — the
#: registry says an attestation of reversibility is good for 30 days, and an
#: attestation resting on a drill older than that is asserting a property
#: nobody has observed inside the window. A caller may TIGHTEN this and cannot
#: widen it; `max_age` is clamped with `min()`.
MAX_DRILL_AGE = timedelta(days=30)

#: The only outcome that attests. Anything else — "failed", "partial",
#: "skipped", or a value this provider does not know — denies. An unrecognised
#: outcome is not read generously: a vocabulary this audit does not understand
#: is not evidence it can score.
RESTORED = "restored"


class RollbackDrillProvider(Provider):
    """Audits a drill log for reversibility that was actually demonstrated.

    Source: a JSONL drill log, one record per rollback drill.

    Eight per-record breaches and one over the sample. The sample-level one is
    the point of the window: a log of last year's drills, audited today,
    produces a fresh attestation about a property nobody has tested since. That
    reads green and is the failure the 30-day window exists to prevent.
    """

    control = "GV-05"
    name = "nx/rollback-drill"

    def __init__(
        self,
        drill_log_path: str | Path = "drill-log.jsonl",
        max_age: timedelta | None = None,
        **config: Any,
    ) -> None:
        self.drill_log_path = Path(drill_log_path)
        # Tighten-only. A config asking for 365 days gets 30.
        self.max_age = min(max_age or MAX_DRILL_AGE, MAX_DRILL_AGE)
        super().__init__(drill_log_path=str(drill_log_path), **config)

    # ---- conformance ---------------------------------------------------

    def positive_control(self) -> bool:
        """The log must exist, parse, and hold at least one drill.

        An empty log is not "no failed drills". It is no drill, and a denial
        from a check with nothing to read proves nothing.
        """
        try:
            return len(list(read_jsonl(self.drill_log_path, what="drill log"))) > 0
        except Exception:  # noqa: BLE001
            return False

    def vacuity_probe(self) -> ProviderResult:
        """Audit the drill that proves nothing. It must FAIL.

        Deliberately not a *failed* drill — one recording `outcome: failed`
        would be caught by a check that only reads that field, and a provider
        that passes its own vacuity probe on the easiest possible breach has
        shown very little. This probe is a drill that reports success, names an
        independent verifier, orders its timestamps correctly, and restores
        every resource it mutated — of which there are none. Every field a
        reviewer would skim is green.
        """
        now = now_utc()
        return self._audit(
            [
                {
                    "drill_id": "vacuity-probe",
                    "performer": "agent-motor",
                    "verifier": "github-ci",
                    "outcome": RESTORED,
                    "mutated": [],
                    "restored": [],
                    "baseline_digest": "sha256:0000",
                    "restored_digest": "sha256:0000",
                    "mutated_at": (now - timedelta(minutes=10)).isoformat(),
                    "rolled_back_at": (now - timedelta(minutes=5)).isoformat(),
                    "verified_at": now.isoformat(),
                }
            ],
            evidence_ref="synthetic://vacuity-probe",
            at=now,
        )

    # ---- the check -----------------------------------------------------

    def check(self) -> ProviderResult:
        try:
            records = list(read_jsonl(self.drill_log_path, what="drill log"))
        except Exception as exc:  # noqa: BLE001
            return ProviderResult.failed(f"drill log unreadable: {exc}")
        return self._audit(records, evidence_ref=f"file://{self.drill_log_path}")

    # ---- internals -----------------------------------------------------

    def _audit(
        self,
        records: list[dict[str, Any]],
        *,
        evidence_ref: str,
        at: datetime | None = None,
    ) -> ProviderResult:
        at = at or now_utc()
        breaches: list[str] = []
        current: list[str] = []

        for record in records:
            drill = record.get("drill_id", "<unidentified>")
            fault = self._breach(record, drill)
            if fault:
                breaches.append(fault)
                continue
            # Only a clean drill counts toward the window. A breached drill
            # inside it is not "recent evidence" of anything.
            try:
                rolled_back = parse_ts(
                    record.get("rolled_back_at"), field="rolled_back_at", where=drill
                )
            except ValueError as exc:  # pragma: no cover - _breach already parsed it
                breaches.append(str(exc))
                continue
            if at - rolled_back <= self.max_age:
                current.append(str(drill))

        if breaches:
            return ProviderResult.failed(
                f"{len(breaches)} of {len(records)} drill(s) do not demonstrate a "
                f"reversal: " + "; ".join(breaches[:5]) + ("..." if len(breaches) > 5 else ""),
                evidence_ref=evidence_ref,
                breaches=len(breaches),
                sampled=len(records),
                current=len(current),
            )

        if not current:
            # Every drill is clean and every drill is old. This is the failure
            # the window exists for, and it is the one that reads greenest:
            # nothing is wrong with the records, there is simply no evidence
            # that reversibility holds *now*.
            return ProviderResult.failed(
                f"no drill within {self.max_age.days}d: {len(records)} clean drill(s) on "
                f"file, newest rolled back more than the window ago. An attestation "
                f"resting on it asserts a property nobody has observed inside the window",
                evidence_ref=evidence_ref,
                breaches=0,
                sampled=len(records),
                current=0,
            )

        return ProviderResult.passed(
            evidence_ref,
            f"{len(current)} of {len(records)} drill(s) reversed a real mutation inside "
            f"{self.max_age.days}d, restored every resource touched, matched the recorded "
            f"baseline, and were verified by an independent principal afterwards",
            breaches=0,
            sampled=len(records),
            current=len(current),
        )

    def _breach(self, record: dict[str, Any], drill: Any) -> str | None:
        """The first reason this drill does not demonstrate a reversal, or None."""
        performer = str(record.get("performer", "")).strip()
        verifier = str(record.get("verifier", "")).strip()

        if not performer:
            return f"{drill}: no performer recorded"
        if not verifier:
            # The performer's word that their own rollback worked.
            return f"{drill}: no verifier recorded"
        if normalise_principal(performer) == normalise_principal(verifier):
            # NX-INV-2 at the drill layer. Aggressively folded, because a
            # collision here DENIES — ADR-0003's rule for which fold to use.
            return f"{drill}: verified by its own performer ({performer})"

        outcome = str(record.get("outcome", "")).strip().lower()
        if outcome != RESTORED:
            return (
                f"{drill}: outcome {outcome or '<unrecorded>'!r} is not {RESTORED!r}"
            )

        mutated = _resources(record.get("mutated"))
        restored = _resources(record.get("restored"))
        if mutated is None:
            return f"{drill}: `mutated` is not a list of resource names"
        if restored is None:
            return f"{drill}: `restored` is not a list of resource names"

        if not mutated:
            # THE ONE WORTH BUILDING FOR. A rollback of nothing restores
            # trivially, passes every other check here, and measures nothing.
            return (
                f"{drill}: mutated nothing, so the rollback reversed nothing. A drill "
                f"against an empty mutation is the vacuous probe with a timestamp on it"
            )

        missing = sorted(set(mutated) - set(restored))
        if missing:
            return (
                f"{drill}: mutated but did not restore {', '.join(missing[:3])}"
                + ("..." if len(missing) > 3 else "")
            )

        baseline = str(record.get("baseline_digest", "")).strip()
        after = str(record.get("restored_digest", "")).strip()
        if not baseline or not after:
            # THE OTHER ONE. Without a comparison, "restored" means the
            # rollback command exited zero — a claim, not a check.
            return (
                f"{drill}: restoration was declared, not compared "
                f"(baseline_digest={baseline or '<absent>'!r}, "
                f"restored_digest={after or '<absent>'!r})"
            )
        if baseline != after:
            return (
                f"{drill}: restored state does not match the baseline "
                f"({baseline} != {after})"
            )

        try:
            mutated_at = parse_ts(record.get("mutated_at"), field="mutated_at", where=drill)
            rolled_back = parse_ts(
                record.get("rolled_back_at"), field="rolled_back_at", where=drill
            )
            verified = parse_ts(record.get("verified_at"), field="verified_at", where=drill)
        except ValueError as exc:
            return str(exc)

        if rolled_back < mutated_at:
            return f"{drill}: rolled back before it was mutated; the record is incoherent"
        if verified <= rolled_back:
            # GV-07 check 4's shape: verification that does not post-date the
            # act is a stamp, not an observation of the result. `<=` because
            # an identical instant is one automated step emitting both.
            return (
                f"{drill}: verified at or before the rollback "
                f"({verified.isoformat()} <= {rolled_back.isoformat()}), so nothing "
                f"observed the restored state"
            )
        return None


def _resources(value: Any) -> list[str] | None:
    """A resource list, or None if the field is not one.

    A string is refused rather than treated as a one-element list: `"mutated":
    "config.yaml"` would otherwise iterate into characters, and a 12-character
    filename would read as 12 mutated resources, every one of them absent from
    `restored`. Fails closed either way, for entirely the wrong reason.
    """
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Iterable):
        return None
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        name = item.strip()
        if name:
            out.append(name)
    return out
