"""L0 lease-log providers — GV-02 authority and GV-06 containment.

Both read one log with two record kinds. The join between them is where the
audits get their teeth: a tally emitted by L0 would be L0 counting its own
compliance, which is the performer-verifies-itself failure moved to the
evidence layer. These providers recompute from the raw records instead.

Record contract: docs/GV-02-GV-06-lease-log-contract.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .base import Provider, ProviderResult
from .builtin import parse_ts, read_jsonl

LEASE = "lease"
ACTION = "action"


def _split(records: Iterable[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Partition the log into leases and actions.

    A record of neither kind is not silently dropped — it is returned to the
    caller as an unknown so the audit can fail on it rather than quietly
    narrowing its own sample.
    """
    leases, actions, unknown = [], [], []
    for record in records:
        kind = str(record.get("record", "")).strip().lower()
        if kind == LEASE:
            leases.append(record)
        elif kind == ACTION:
            actions.append(record)
        else:
            unknown.append(record)
    if unknown:
        raise ValueError(
            f"{len(unknown)} record(s) declare no recognised 'record' kind; "
            "an unclassified record would narrow the sample without saying so"
        )
    return leases, actions


class _LeaseLogProvider(Provider):
    """Shared plumbing: one log path, one reader, one split."""

    def __init__(self, lease_log_path: str | Path = "lease-log.jsonl", **config: Any) -> None:
        self.lease_log_path = Path(lease_log_path)
        super().__init__(lease_log_path=str(lease_log_path), **config)

    def _load(self) -> tuple[list[dict], list[dict]]:
        return _split(read_jsonl(self.lease_log_path, what="lease log"))

    @property
    def _evidence(self) -> str:
        return f"file://{self.lease_log_path}"


class LeaseAuthorityProvider(_LeaseLogProvider):
    """GV-02 — every action resolves to an explicit lease before execution."""

    control = "GV-02"
    name = "l0/lease-audit"

    # ---- conformance ---------------------------------------------------

    def positive_control(self) -> bool:
        """At least one action must be present. No actions is no evidence."""
        try:
            _, actions = self._load()
        except Exception:  # noqa: BLE001
            return False
        return len(actions) > 0

    def vacuity_probe(self) -> ProviderResult:
        """An action that ran before its lease was issued. Must FAIL."""
        return self._audit(
            leases=[
                {
                    "record": LEASE, "lease_id": "L-probe", "principal": "agent-x",
                    "issued_by": "l0-gate",
                    "issued_at": "2026-01-01T10:00:00+00:00",
                    "expires_at": "2026-01-01T11:00:00+00:00",
                    "scope": ["tool:git"],
                }
            ],
            actions=[
                {
                    "record": ACTION, "action_id": "a-probe", "lease_id": "L-probe",
                    "at": "2026-01-01T09:00:00+00:00", "scope": "tool:git",
                }
            ],
            evidence_ref="synthetic://vacuity-probe",
        )

    # ---- the check -----------------------------------------------------

    def check(self) -> ProviderResult:
        try:
            leases, actions = self._load()
        except Exception as exc:  # noqa: BLE001
            return ProviderResult.failed(f"lease log unreadable: {exc}")
        return self._audit(leases=leases, actions=actions, evidence_ref=self._evidence)

    @staticmethod
    def _audit(*, leases: list[dict], actions: list[dict], evidence_ref: str) -> ProviderResult:
        breaches: list[str] = []
        by_id: dict[str, dict] = {}

        # ---- lease-level: self-issuance and standing grants
        for lease in leases:
            lid = lease.get("lease_id") or "<unidentified>"
            principal = lease.get("principal")
            issuer = lease.get("issued_by")

            if not principal:
                breaches.append(f"lease {lid}: no principal recorded")
                continue
            if not issuer:
                breaches.append(f"lease {lid}: no issuer recorded")
                continue
            if issuer == principal:
                # A component that can grant itself authority has none.
                breaches.append(f"lease {lid}: self-issued by {principal}")
                continue
            if not lease.get("expires_at"):
                # D-03 makes leases fail-closed and time-boxed; an absent TTL
                # is a standing grant, which is that failure already complete.
                breaches.append(f"lease {lid}: standing lease, no expiry")
                continue
            if lid in by_id:
                breaches.append(f"lease {lid}: duplicate lease id")
                continue
            by_id[lid] = lease

        # ---- action-level: the join
        for action in actions:
            aid = action.get("action_id") or "<unidentified>"
            lid = action.get("lease_id")

            if not lid:
                breaches.append(f"action {aid}: no lease claimed")
                continue
            lease = by_id.get(lid)
            if lease is None:
                breaches.append(f"action {aid}: claims lease {lid}, which is not in the log")
                continue

            try:
                at = parse_ts(action.get("at"), field="at", where=f"action {aid}")
                issued = parse_ts(lease.get("issued_at"), field="issued_at", where=f"lease {lid}")
                expires = parse_ts(lease.get("expires_at"), field="expires_at", where=f"lease {lid}")
            except ValueError as exc:
                breaches.append(str(exc))
                continue

            if at < issued:
                # Post-hoc authorisation: the record looks complete, and the
                # action was not authorised at the moment it ran.
                breaches.append(
                    f"action {aid}: executed at {at.isoformat()}, before lease {lid} "
                    f"was issued at {issued.isoformat()}"
                )
                continue
            if at > expires:
                breaches.append(f"action {aid}: executed after lease {lid} expired")
                continue

            granted = lease.get("scope") or []
            if not isinstance(granted, list) or not granted:
                breaches.append(f"lease {lid}: no granted scope, so it bounds nothing")
                continue
            used = action.get("scope")
            if not used:
                breaches.append(f"action {aid}: no scope recorded")
                continue
            if used not in granted:
                breaches.append(f"action {aid}: scope {used!r} outside lease {lid}")

        sampled = len(actions)
        if breaches:
            return ProviderResult.failed(
                f"{len(breaches)} authority breach(es) across {sampled} action(s) and "
                f"{len(leases)} lease(s): " + "; ".join(breaches[:5])
                + ("..." if len(breaches) > 5 else ""),
                evidence_ref=evidence_ref,
                breaches=len(breaches), sampled=sampled, leases=len(leases),
            )
        return ProviderResult.passed(
            evidence_ref,
            f"all {sampled} action(s) resolved to a live, in-scope lease issued by "
            f"another principal before execution",
            breaches=0, sampled=sampled, leases=len(leases),
        )


class LeaseContainmentProvider(_LeaseLogProvider):
    """GV-06 — blast radius bounded by declared, enforced ceilings."""

    control = "GV-06"
    name = "l0/scope-budget"

    # ---- conformance ---------------------------------------------------

    def positive_control(self) -> bool:
        """At least one lease must be present. No leases is no evidence."""
        try:
            leases, _ = self._load()
        except Exception:  # noqa: BLE001
            return False
        return len(leases) > 0

    def vacuity_probe(self) -> ProviderResult:
        """A lease that blew its token ceiling. Must FAIL."""
        return self._audit(
            [
                {
                    "record": LEASE, "lease_id": "L-probe", "principal": "agent-x",
                    "ceilings": {"tokens": 1000},
                    "consumed": {"tokens": 5000},
                }
            ],
            evidence_ref="synthetic://vacuity-probe",
        )

    # ---- the check -----------------------------------------------------

    def check(self) -> ProviderResult:
        try:
            leases, _ = self._load()
        except Exception as exc:  # noqa: BLE001
            return ProviderResult.failed(f"lease log unreadable: {exc}")
        return self._audit(leases, evidence_ref=self._evidence)

    @staticmethod
    def _audit(leases: list[dict], *, evidence_ref: str) -> ProviderResult:
        breaches: list[str] = []

        for lease in leases:
            lid = lease.get("lease_id") or "<unidentified>"
            principal = lease.get("principal")
            ceilings = lease.get("ceilings")
            consumed = lease.get("consumed") or {}

            if not isinstance(ceilings, dict) or not ceilings:
                # Containment that declares no limit bounds nothing.
                breaches.append(f"lease {lid}: unbounded grant, no ceilings declared")
                continue
            if not isinstance(consumed, dict):
                breaches.append(f"lease {lid}: 'consumed' is not an object")
                continue

            amended_by = lease.get("ceilings_amended_by")
            if amended_by and amended_by == principal:
                # D-01: a component that can widen its own envelope has no envelope.
                breaches.append(f"lease {lid}: ceilings widened by the principal they bound")
                continue

            for metric, used in consumed.items():
                limit = ceilings.get(metric)
                if limit is None:
                    breaches.append(
                        f"lease {lid}: consumed {metric!r} with no ceiling declared for it"
                    )
                    continue
                try:
                    if float(used) > float(limit):
                        # The ceiling was recorded and not applied: advisory,
                        # not enforced. KBS-INV-3, measured.
                        breaches.append(
                            f"lease {lid}: {metric} consumed {used} over ceiling {limit}"
                        )
                except (TypeError, ValueError):
                    breaches.append(f"lease {lid}: {metric} is not numeric ({used!r} vs {limit!r})")

        if breaches:
            return ProviderResult.failed(
                f"{len(breaches)} containment breach(es) across {len(leases)} lease(s): "
                + "; ".join(breaches[:5]) + ("..." if len(breaches) > 5 else ""),
                evidence_ref=evidence_ref,
                breaches=len(breaches), sampled=len(leases),
            )
        return ProviderResult.passed(
            evidence_ref,
            f"all {len(leases)} lease(s) declared ceilings covering every resource "
            f"consumed, and none were exceeded",
            breaches=0, sampled=len(leases),
        )
