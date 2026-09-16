"""Expiring, recorded waivers for the Capability-Authority Gate.

ILR-001-DR D-05 rules that a real programme needs an exception path, and that
an exception path with no expiry is how a temporary control gap becomes the
permanent architecture. This module is that path. It carries the four
properties the ruling requires, and one the ruling implies:

  1. Every waiver names the control it waives, the bands it covers, a human
     accountable for it, a compensating control, a ratification reference and
     a hard expiry. A blank in any of those is a malformed record, not a
     lenient one.
  2. Expiry is evaluated on read. Nothing has to run for a waiver to lapse,
     so a waiver outlives the scheduler that was supposed to retire it by
     exactly zero seconds.
  3. The controls ILR-001-DR D-06 declares non-compensable cannot be waived
     at all -- at any TTL, by anyone, with any compensating control.
  4. A waiver never licenses the principal that issued it or the principal
     accountable for it. Accountability that can license its own holder is
     not accountability; this is NX-INV-2 applied to the exception path.

The bounds are ceilings in code, not merely defaults in the registry. A
registry may tighten them and may name further non-compensable controls; it
cannot loosen either. An earlier cut of this module read the bounds from the
registry alone, which meant that deleting four lines of YAML made the four
integrity controls waivable -- the exact inversion the ruling forbids, reached
by omission rather than by argument.

Two failure kinds are deliberately distinguished:

  * A *malformed* waiver raises WaiverError at load. The operator wrote
    something that is not a waiver, and a half-read waiver file would
    under-constrain the gate exactly as a half-read registry would.
  * A *policy trigger* -- more active waivers than the cap allows -- does not
    raise. It voids every waiver until the situation is corrected, which is
    fail-closed, and it is reported by `triggers()` and `void_reason()` so the
    D-05 reversal condition is detectable rather than remembered.

What this module cannot do: `issued_by`, `accountable` and a request's
`identity` are self-declared strings on an unauthenticated substrate. The
self-waiver ban compares what the record claims against what the request
claims, and neither is bound to an authenticated subject until KBS-001 T1
issues real identities. Until then the ban stops an honest mistake and a
careless script, not a determined author of the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .errors import WaiverError
from .model import has_invisible, normalise_principal, now_utc

__all__ = ["NON_COMPENSABLE_FLOOR", "Waiver", "WaiverPolicy", "WaiverRegister"]

#: ILR-001-DR D-06. Integrity controls, non-compensable by human process: an
#: append-only sink a human promises not to rewrite is a rewritable sink, and
#: external attestation performed by an internal party is not external. This
#: set is a floor in code. A registry may add to it and may not remove from it.
NON_COMPENSABLE_FLOOR = frozenset({"GV-01", "GV-02", "GV-03", "GV-08"})

#: Ceilings, likewise not lowerable by configuration.
MAX_TTL_CEILING = timedelta(days=90)
MAX_ACTIVE_CEILING = 2
MAX_RENEWALS_CEILING = 1


# ---- field parsing -----------------------------------------------------


def _clean(value: Any, key: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WaiverError(
            f"{where}: {key!r} must be a non-empty string; "
            "a blank accountability field is not an accountability record"
        )
    if has_invisible(value):
        raise WaiverError(
            f"{where}: {key!r} contains an invisible or control character. A name "
            "that renders as one principal and compares as another is how the "
            "self-waiver rule is bypassed"
        )
    return value.strip()


def _timestamp(payload: Mapping[str, Any], key: str, where: str) -> datetime:
    raw = payload.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise WaiverError(f"{where}: {key!r} must be an ISO-8601 timestamp string")
    try:
        value = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise WaiverError(f"{where}: {key!r} is not a valid timestamp: {exc}") from exc
    if value.tzinfo is None:
        raise WaiverError(
            f"{where}: {key!r} carries no timezone; a naive expiry lapses in whatever "
            "zone the reader happens to be in, which is not a hard expiry"
        )
    return value


def _bands(value: Any, where: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise WaiverError(
            f"{where}: 'bands' must be a list of band ids. A bare string is not a "
            "list: membership on it is substring matching, so 'BAND-B BAND-D' "
            "would silently also cover 'AND-B'"
        )
    bands: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise WaiverError(f"{where}: 'bands' entry {item!r} is not a band id")
        bands.append(item.strip())
    if not bands:
        raise WaiverError(f"{where}: 'bands' is empty; name the bands this waiver licenses")
    if len(set(bands)) != len(bands):
        raise WaiverError(f"{where}: 'bands' contains duplicates: {tuple(bands)}")
    return tuple(bands)


# ---- the record --------------------------------------------------------


@dataclass(frozen=True)
class Waiver:
    """One recorded, expiring exception to the Capability-Authority Gate."""

    id: str
    control: str
    bands: tuple[str, ...]
    accountable: str
    issued_by: str
    compensating_control: str
    ratification_ref: str
    issued_at: datetime
    expires_at: datetime
    renews: str | None = None

    def __post_init__(self) -> None:
        """Validate on construction, not only on parse.

        `from_dict` is not the only way a Waiver is built -- callers and tests
        construct one directly -- and a dataclass that validates in its parser
        validates nothing at all for those. The checks live here so there is
        one door.
        """
        for key in (
            "id",
            "control",
            "accountable",
            "issued_by",
            "compensating_control",
            "ratification_ref",
        ):
            object.__setattr__(self, key, _clean(getattr(self, key), key, f"waiver {self.id!r}"))
        object.__setattr__(self, "bands", _bands(self.bands, f"waiver {self.id!r}"))
        for key in ("issued_at", "expires_at"):
            value = getattr(self, key)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise WaiverError(
                    f"waiver {self.id}: {key} must be a timezone-aware datetime"
                )
        if self.expires_at <= self.issued_at:
            raise WaiverError(
                f"waiver {self.id}: expires_at ({self.expires_at.isoformat()}) is not "
                f"after issued_at ({self.issued_at.isoformat()}); a waiver that "
                "expires before it begins is a record, not a control"
            )
        if self.renews is not None:
            object.__setattr__(
                self, "renews", _clean(self.renews, "renews", f"waiver {self.id!r}")
            )
            if self.renews == self.id:
                raise WaiverError(f"waiver {self.id}: renews itself")

    @property
    def ttl(self) -> timedelta:
        return self.expires_at - self.issued_at

    @property
    def principals(self) -> frozenset[str]:
        """Identities this waiver must never license, as comparison keys.

        Both the issuer and the accountable party. A waiver that licenses its
        own issuer is self-granted authority wearing an exception's name.
        """
        return frozenset(
            {normalise_principal(self.issued_by), normalise_principal(self.accountable)}
        ) - {""}

    def is_active(self, at: datetime) -> bool:
        """Active on [issued_at, expires_at).

        Half-open deliberately: at the expiry instant the waiver is expired.
        The boundary resolves against the waiver, as every other boundary in
        this package resolves against the permission.
        """
        return self.issued_at <= at < self.expires_at

    def covers(self, control: str, band: str) -> bool:
        return control == self.control and band in self.bands

    def scopes(self) -> tuple[tuple[str, str], ...]:
        return tuple((self.control, band) for band in self.bands)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "control": self.control,
            "bands": list(self.bands),
            "accountable": self.accountable,
            "issued_by": self.issued_by,
            "compensating_control": self.compensating_control,
            "ratification_ref": self.ratification_ref,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "renews": self.renews,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, where: str = "waiver") -> "Waiver":
        if not isinstance(payload, Mapping):
            raise WaiverError(f"{where}: waiver record must be a JSON object")
        renews = payload.get("renews")
        if renews is not None and not isinstance(renews, str):
            raise WaiverError(
                f"{where}: 'renews' must be omitted, null, or the id of the waiver "
                "this one replaces"
            )
        return cls(
            id=_clean(payload.get("id"), "id", where),
            control=_clean(payload.get("control"), "control", where),
            bands=_bands(payload.get("bands"), where),
            accountable=_clean(payload.get("accountable"), "accountable", where),
            issued_by=_clean(payload.get("issued_by"), "issued_by", where),
            compensating_control=_clean(
                payload.get("compensating_control"), "compensating_control", where
            ),
            ratification_ref=_clean(
                payload.get("ratification_ref"), "ratification_ref", where
            ),
            issued_at=_timestamp(payload, "issued_at", where),
            expires_at=_timestamp(payload, "expires_at", where),
            renews=renews,
        )


# ---- policy ------------------------------------------------------------


@dataclass(frozen=True)
class WaiverPolicy:
    """Bounds on the exception path. Registry-tightenable, never loosenable."""

    non_compensable: frozenset[str] = NON_COMPENSABLE_FLOOR
    max_ttl: timedelta = MAX_TTL_CEILING
    max_active: int = MAX_ACTIVE_CEILING
    max_renewals: int = MAX_RENEWALS_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "non_compensable", frozenset(self.non_compensable) | NON_COMPENSABLE_FLOOR
        )
        object.__setattr__(self, "max_ttl", min(self.max_ttl, MAX_TTL_CEILING))
        object.__setattr__(self, "max_active", min(self.max_active, MAX_ACTIVE_CEILING))
        object.__setattr__(self, "max_renewals", min(self.max_renewals, MAX_RENEWALS_CEILING))


# ---- the register ------------------------------------------------------


class WaiverRegister:
    """A validated set of waivers, evaluated against a policy.

    Structural validation happens once, at construction. Activity and the
    reversal-trigger state are evaluated per call, because both are functions
    of the clock and caching either would reintroduce the sweep this design
    exists to avoid.
    """

    def __init__(
        self,
        waivers: Iterable[Waiver] = (),
        *,
        policy: WaiverPolicy | None = None,
        known_controls: Iterable[str] | None = None,
        known_bands: Iterable[str] | None = None,
    ) -> None:
        self.policy = policy or WaiverPolicy()
        self._waivers: tuple[Waiver, ...] = tuple(
            sorted(waivers, key=lambda w: (w.issued_at, w.id))
        )
        self._by_id: dict[str, Waiver] = {}
        for waiver in self._waivers:
            if waiver.id in self._by_id:
                raise WaiverError(
                    f"duplicate waiver id {waiver.id!r}; ids are the audit handle and "
                    "must identify exactly one record"
                )
            self._by_id[waiver.id] = waiver
        self._validate(known_controls, known_bands)

    # ---- construction --------------------------------------------------

    @classmethod
    def empty(cls, policy: WaiverPolicy | None = None) -> "WaiverRegister":
        return cls((), policy=policy)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        policy: WaiverPolicy | None = None,
        known_controls: Iterable[str] | None = None,
        known_bands: Iterable[str] | None = None,
    ) -> "WaiverRegister":
        """Load waivers from a JSON lines file. An absent file means none."""
        path = Path(path)
        if not path.is_file():
            return cls((), policy=policy, known_controls=known_controls, known_bands=known_bands)
        records: list[Waiver] = []
        # split("\n") rather than splitlines(), for the reason given in
        # attestation.py: splitlines() also breaks on \v \f \x85 and U+2028/9,
        # which are legal inside a JSON string and invisible to every line
        # counter an auditor would use.
        text = path.read_text(encoding="utf-8-sig")
        for lineno, line in enumerate(text.split("\n"), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            where = f"{path}:{lineno}"
            try:
                payload = json.loads(line)
            except ValueError as exc:
                raise WaiverError(f"{where}: malformed JSON: {exc}") from exc
            records.append(Waiver.from_dict(payload, where=where))
        return cls(records, policy=policy, known_controls=known_controls, known_bands=known_bands)

    @classmethod
    def for_registry(
        cls, registry: Any, path: str | Path | None = None, waivers: Iterable[Waiver] = ()
    ) -> "WaiverRegister":
        """Build a register bound to a registry's policy and vocabulary."""
        kwargs = {
            "policy": registry.waiver_policy,
            "known_controls": registry.controls.keys(),
            "known_bands": registry.bands.keys(),
        }
        if path is not None:
            return cls.from_file(path, **kwargs)
        return cls(waivers, **kwargs)

    # ---- validation ----------------------------------------------------

    def _validate(
        self, known_controls: Iterable[str] | None, known_bands: Iterable[str] | None
    ) -> None:
        controls = set(known_controls) if known_controls is not None else None
        bands = set(known_bands) if known_bands is not None else None

        for waiver in self._waivers:
            if waiver.control in self.policy.non_compensable:
                raise WaiverError(
                    f"waiver {waiver.id}: {waiver.control} is non-compensable "
                    "(ILR-001-DR D-06). An integrity control has no waiver path: an "
                    "append-only sink a human promises not to rewrite is a rewritable "
                    "sink, and external attestation performed internally is not external"
                )
            if controls is not None and waiver.control not in controls:
                raise WaiverError(
                    f"waiver {waiver.id}: {waiver.control} is not a defined control"
                )
            if bands is not None:
                unknown = [b for b in waiver.bands if b not in bands]
                if unknown:
                    raise WaiverError(
                        f"waiver {waiver.id}: undefined band(s) {', '.join(unknown)}"
                    )
            if waiver.ttl > self.policy.max_ttl:
                raise WaiverError(
                    f"waiver {waiver.id}: TTL {waiver.ttl} exceeds the maximum "
                    f"{self.policy.max_ttl}. A waiver longer than the bound is a "
                    "standing waiver, which D-05 forbids by name"
                )

        self._assert_renewal_chains()
        self._assert_one_chain_per_scope()

    def _assert_renewal_chains(self) -> None:
        """Every renewal resolves, stays on its own control, and stays shallow."""
        renewed_by: dict[str, list[str]] = {}
        for waiver in self._waivers:
            if waiver.renews is not None:
                renewed_by.setdefault(waiver.renews, []).append(waiver.id)
        for target, successors in renewed_by.items():
            if len(successors) > 1:
                # Otherwise a star of N waivers all pointing at one root each
                # measures depth 1, and the renewal cap never fires however
                # many times the same gap is extended.
                raise WaiverError(
                    f"waiver {target} is renewed by more than one record "
                    f"({', '.join(sorted(successors))}). A waiver has at most one "
                    "successor; parallel renewals reset the renewal count"
                )

        for waiver in self._waivers:
            depth = 0
            seen = {waiver.id}
            current = waiver
            while current.renews is not None:
                predecessor = self._by_id.get(current.renews)
                if predecessor is None:
                    raise WaiverError(
                        f"waiver {waiver.id}: renews {current.renews!r}, which is not in "
                        "this register. A renewal whose predecessor is absent resets the "
                        "renewal count, which is how a twice-renewed waiver becomes a "
                        "fresh one"
                    )
                if predecessor.id in seen:
                    raise WaiverError(
                        f"waiver {waiver.id}: renewal cycle through {predecessor.id}"
                    )
                if predecessor.control != waiver.control:
                    raise WaiverError(
                        f"waiver {waiver.id}: renews {predecessor.id}, which waives "
                        f"{predecessor.control}, not {waiver.control}. A renewal that "
                        "changes control is a new waiver claiming an inherited history"
                    )
                seen.add(predecessor.id)
                depth += 1
                if depth > self.policy.max_renewals:
                    raise WaiverError(
                        f"waiver {waiver.id}: renewal depth {depth} exceeds the maximum "
                        f"{self.policy.max_renewals} (ILR-001-DR D-05 reversal trigger). "
                        "A waiver needing this many renewals means the matrix is "
                        "mis-calibrated; re-cut it rather than renewing again"
                    )
                current = predecessor

    def _assert_one_chain_per_scope(self) -> None:
        """At most one un-renewing waiver per (control, band).

        Without this, the TTL ceiling and the renewal cap are both defeated by
        tiling: a series of unlinked waivers, each individually inside the
        90-day bound and never more than one active, covers an unbounded span
        and arms no trigger. Forcing every later waiver on the same scope to
        declare `renews` puts it under the renewal counter, where two windows
        is the end of it.
        """
        roots: dict[tuple[str, str], str] = {}
        for waiver in self._waivers:
            if waiver.renews is not None:
                continue
            for scope in waiver.scopes():
                first = roots.get(scope)
                if first is not None:
                    raise WaiverError(
                        f"waiver {waiver.id}: {scope[0]} on {scope[1]} is already waived "
                        f"by {first}, which this record does not renew. Successive "
                        "waivers on one scope must declare `renews`, or the renewal "
                        "cap means nothing"
                    )
                roots[scope] = waiver.id

    # ---- evaluation ----------------------------------------------------

    def active(self, at: datetime | None = None) -> tuple[Waiver, ...]:
        """Waivers whose window contains `at`, ignoring the cap."""
        at = at or now_utc()
        return tuple(w for w in self._waivers if w.is_active(at))

    def effective(self, at: datetime | None = None) -> tuple[Waiver, ...]:
        """Waivers that actually license anything. Empty while over the cap."""
        at = at or now_utc()
        active = self.active(at)
        return () if len(active) > self.policy.max_active else active

    def over_cap(self, at: datetime | None = None) -> bool:
        return len(self.active(at)) > self.policy.max_active

    def void_reason(self, at: datetime | None = None) -> str | None:
        """Why no waiver applies at `at`, when that is a policy state.

        Reported so a denial can say that a covering waiver existed and was
        voided, rather than presenting the control as simply unattested. The
        difference matters: one is work to do, the other is a waiver file to
        fix, and a denial that cannot tell them apart gets fixed by adding
        another waiver.
        """
        at = at or now_utc()
        count = len(self.active(at))
        if count <= self.policy.max_active:
            return None
        return (
            f"all waivers are void: {count} active exceeds the maximum "
            f"{self.policy.max_active} (ILR-001-DR D-05). Re-cut the matrix rather "
            "than adding another exception"
        )

    def covering(
        self,
        control: str,
        band: str,
        *,
        at: datetime | None = None,
        claimed: Iterable[str] = (),
    ) -> Waiver | None:
        """The waiver licensing `control` for `band` for this caller, or None."""
        at = at or now_utc()
        blocked = self._claimed(claimed)
        for waiver in self.effective(at):
            if waiver.covers(control, band) and not (blocked & waiver.principals):
                return waiver
        return None

    def excluded(
        self,
        control: str,
        band: str,
        *,
        at: datetime | None = None,
        claimed: Iterable[str] = (),
    ) -> Waiver | None:
        """A waiver that matches but is withheld because the caller is its own.

        Reported separately so a denial can say *why* an apparently applicable
        waiver did not apply. Silence here is how an operator concludes the
        waiver file is broken and writes a second one.
        """
        at = at or now_utc()
        blocked = self._claimed(claimed)
        if not blocked:
            return None
        for waiver in self.effective(at):
            if waiver.covers(control, band) and (blocked & waiver.principals):
                return waiver
        return None

    def triggers(self, at: datetime | None = None) -> tuple[str, ...]:
        """Armed ILR-001-DR reversal conditions, as human-readable lines."""
        at = at or now_utc()
        armed: list[str] = []
        void = self.void_reason(at)
        if void is not None:
            armed.append(f"D-05: {void}")
        for waiver in self.active(at):
            if waiver.renews is not None:
                armed.append(
                    f"D-05: waiver {waiver.id} is a renewal of {waiver.renews}; "
                    f"the next renewal on this scope is refused at load (max depth "
                    f"{self.policy.max_renewals})"
                )
        return tuple(armed)

    @staticmethod
    def _claimed(claimed: Iterable[str]) -> frozenset[str]:
        return frozenset(normalise_principal(c) for c in claimed if c) - {""}

    # ---- persistence and access ----------------------------------------

    @staticmethod
    def append_to_file(path: str | Path, waiver: Waiver) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(waiver.to_dict(), sort_keys=True) + "\n")

    def get(self, waiver_id: str) -> Waiver | None:
        return self._by_id.get(waiver_id)

    def __iter__(self) -> Iterator[Waiver]:
        return iter(self._waivers)

    def __len__(self) -> int:
        return len(self._waivers)

    def __bool__(self) -> bool:
        # A register with no waivers is still a valid register; truthiness
        # follows length so `if waivers:` reads as "are there any".
        return bool(self._waivers)
