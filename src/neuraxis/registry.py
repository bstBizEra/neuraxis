"""Registry loading and validation.

The registry is kernel (KBS-001, K-04 family). This module refuses to load a
registry it cannot fully validate — there is no partial or default registry,
because a half-loaded registry would silently under-constrain the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

import yaml

from .errors import CycleError, RegistryError, UnknownCapabilityError, UnknownControlError
from .model import Band, Capability, GVControl, Risk

DEFAULT_REGISTRY = Path(__file__).parent / "config" / "neuraxis.yaml"

_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parse '24h' style durations. Rejects anything else rather than defaulting."""
    match = _DURATION.match(str(text).strip())
    if not match:
        raise RegistryError(f"invalid duration {text!r}; expected forms like '30m', '24h', '7d'")
    value, unit = int(match.group(1)), match.group(2)
    if value <= 0:
        raise RegistryError(f"duration must be positive, got {text!r}")
    return timedelta(**{_UNITS[unit]: value})


@dataclass(frozen=True)
class Registry:
    """Validated, immutable view of the Neuraxis registry."""

    framework: str
    version: str
    principle: str
    controls: Mapping[str, GVControl]
    capabilities: Mapping[str, Capability]
    bands: Mapping[str, Band]
    role_grants: Mapping[str, tuple[str, ...]]
    non_delegable: frozenset[str]
    escalate_at_risk: Risk
    attestation_max_age: timedelta
    on_missing_attestation: str
    enforcement_mode: str
    thresholds: Mapping[str, Mapping[str, float]]

    # ---- lookups -------------------------------------------------------

    def max_age_for(self, control_id: str) -> timedelta:
        """The control's own attestation window, or the registry default.

        An unknown control returns the default rather than raising: callers
        reach this from the deny path, and a lookup failure there must not
        convert a denial into an exception.
        """
        control = self.controls.get(control_id)
        return control.max_age if control else self.attestation_max_age

    def capability(self, capability_id: str) -> Capability:
        try:
            return self.capabilities[capability_id]
        except KeyError:
            raise UnknownCapabilityError(
                f"{capability_id} is not in the registry; an unknown capability is an ungoverned one"
            ) from None

    def band(self, band_id: str) -> Band:
        try:
            return self.bands[band_id]
        except KeyError:
            raise RegistryError(f"unknown band {band_id}") from None

    def band_closure(self, band_id: str) -> tuple[str, ...]:
        """All bands that must be attained for `band_id`, including itself.

        Returned in dependency order so callers can report the first blocker.
        """
        seen: list[str] = []
        stack = [band_id]
        guard = 0
        while stack:
            guard += 1
            if guard > len(self.bands) * len(self.bands) + 10:
                raise CycleError(f"cycle reached while resolving {band_id}")
            current = stack.pop()
            if current in seen:
                continue
            band = self.band(current)
            unresolved = [d for d in band.depends_on if d not in seen]
            if unresolved:
                stack.append(current)
                stack.extend(unresolved)
                continue
            seen.append(current)
        return tuple(seen)

    def roles_granting(self, band_id: str) -> tuple[str, ...]:
        return tuple(sorted(r for r, bands in self.role_grants.items() if band_id in bands))

    def threshold(self, band_id: str) -> Mapping[str, float]:
        return self.thresholds.get(band_id, {})


# ---- loading -----------------------------------------------------------


def _require(data: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise RegistryError(f"{where}: missing required key {key!r}")
    return data[key]


def load_registry(path: str | Path | None = None) -> Registry:
    """Load and fully validate a registry file.

    Raises RegistryError on any inconsistency. Callers must not catch and
    continue: the gate treats an unloadable registry as deny-everything.
    """
    path = Path(path) if path else DEFAULT_REGISTRY
    if not path.is_file():
        raise RegistryError(f"registry not found at {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"registry {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise RegistryError(f"registry {path} must be a mapping at top level")

    enforcement = raw.get("enforcement", {}) or {}
    default_max_age = parse_duration(enforcement.get("attestation_max_age", "24h"))

    controls = {
        cid: GVControl(
            id=cid,
            name=_require(body, "name", cid),
            attestation=_require(body, "attestation", cid),
            max_age=(
                parse_duration(body["max_age"]) if "max_age" in body else default_max_age
            ),
        )
        for cid, body in _require(raw, "governance", "root").items()
    }
    if not controls:
        raise RegistryError("registry defines no governance controls")

    capabilities = {
        cid: Capability(
            id=cid,
            name=_require(body, "name", cid),
            band=_require(body, "band", cid),
            question=_require(body, "question", cid),
        )
        for cid, body in _require(raw, "capabilities", "root").items()
    }
    if not capabilities:
        raise RegistryError("registry defines no capabilities")

    bands: dict[str, Band] = {}
    for bid, body in _require(raw, "bands", "root").items():
        requires = tuple(body.get("requires", ()))
        if not requires:
            # A band with no required controls is unconditionally attained,
            # which makes it a capability grant wearing a band's name.
            raise RegistryError(
                f"band {bid} requires no controls; a band that requires nothing "
                "licenses everything and is not a band"
            )
        for control in requires:
            if control not in controls:
                raise UnknownControlError(f"band {bid} requires undefined control {control}")
        bands[bid] = Band(
            id=bid,
            capabilities=tuple(sorted(c for c, cap in capabilities.items() if cap.band == bid)),
            requires=requires,
            depends_on=tuple(body.get("depends_on", ())),
        )

    # Every capability must belong to a declared band, and every band must be
    # reachable. Both directions, because either gap is an ungoverned path.
    for cap in capabilities.values():
        if cap.band not in bands:
            raise RegistryError(f"capability {cap.id} references undefined band {cap.band}")
    for band in bands.values():
        for dep in band.depends_on:
            if dep not in bands:
                raise RegistryError(f"band {band.id} depends on undefined band {dep}")
        if not band.capabilities:
            raise RegistryError(f"band {band.id} contains no capabilities")

    _assert_acyclic(bands)

    authority = raw.get("authority", {}) or {}
    role_grants = {
        role: tuple(grants) for role, grants in (authority.get("role_grants", {}) or {}).items()
    }
    for role, grants in role_grants.items():
        for band_id in grants:
            if band_id not in bands:
                raise RegistryError(f"role {role} granted undefined band {band_id}")

    non_delegable = frozenset(authority.get("non_delegable", ()) or ())
    for cid in non_delegable:
        if cid not in capabilities:
            raise RegistryError(f"non_delegable references undefined capability {cid}")

    try:
        escalate_at_risk = Risk(str(authority.get("escalate_at_risk", "CRITICAL")).upper())
    except ValueError as exc:
        raise RegistryError(f"invalid escalate_at_risk: {exc}") from exc

    on_missing = str(enforcement.get("on_missing_attestation", "deny")).lower()
    if on_missing != "deny":
        # The only conformant value. A registry that allows on missing
        # attestation is not a Neuraxis registry.
        raise RegistryError(
            f"on_missing_attestation must be 'deny', got {on_missing!r} "
            "(NX-INV-1 requires fail-closed enforcement)"
        )

    thresholds = {
        bid: {k: float(v) for k, v in vals.items()}
        for bid, vals in ((raw.get("scorecard", {}) or {}).get("thresholds", {}) or {}).items()
    }
    for bid in thresholds:
        if bid not in bands:
            raise RegistryError(f"scorecard threshold references undefined band {bid}")

    return Registry(
        framework=str(_require(raw, "framework", "root")),
        version=str(_require(raw, "version", "root")),
        principle=str(raw.get("principle", "governed-evolution")),
        controls=controls,
        capabilities=capabilities,
        bands=bands,
        role_grants=role_grants,
        non_delegable=non_delegable,
        escalate_at_risk=escalate_at_risk,
        attestation_max_age=default_max_age,
        on_missing_attestation=on_missing,
        enforcement_mode=str(enforcement.get("mode", "l0-mechanical")),
        thresholds=thresholds,
    )


def _assert_acyclic(bands: Mapping[str, Band]) -> None:
    """Depth-first cycle detection over band dependencies."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {bid: WHITE for bid in bands}

    def visit(bid: str, trail: tuple[str, ...]) -> None:
        if colour[bid] == GREY:
            raise CycleError(f"band dependency cycle: {' -> '.join(trail + (bid,))}")
        if colour[bid] == BLACK:
            return
        colour[bid] = GREY
        for dep in bands[bid].depends_on:
            visit(dep, trail + (bid,))
        colour[bid] = BLACK

    for bid in bands:
        visit(bid, ())
