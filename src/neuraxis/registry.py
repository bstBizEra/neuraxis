"""Registry loading and validation.

The registry is kernel (KBS-001, K-04 family). This module refuses to load a
registry it cannot fully validate — there is no partial or default registry,
because a half-loaded registry would silently under-constrain the gate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

import yaml

from .errors import CycleError, RegistryError, UnknownCapabilityError, UnknownControlError
from .envelope import EnvelopePolicy, MAX_ENVELOPE_TTL_CEILING
from .model import Band, Capability, GVControl, Risk
from .waiver import WaiverPolicy

DEFAULT_REGISTRY = Path(__file__).parent / "config" / "neuraxis.yaml"

_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def registry_digest(path: str | Path | None = None) -> tuple[str, Path]:
    """SHA-256 of the registry file, and the path it was read from.

    Hashes the bytes on disk, not the parsed document. The digest has to match
    what `sha256sum` prints and what `release.yml` records, because the whole
    point is that an operator can compare the kernel config they are running
    against the version that was ratified -- and they will do it with the tool
    that is already on the machine, not with this one.

    KBS-001 K-09. The roadmap prescribes a weekly drift check of the registry
    against its ratified version; that sentence was inert until releases began
    carrying a digest.
    """
    path = Path(path) if path else DEFAULT_REGISTRY
    if not path.is_file():
        raise RegistryError(f"registry not found at {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest(), path


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
    waiver_policy: WaiverPolicy = field(default_factory=WaiverPolicy)
    envelope_policy: EnvelopePolicy = field(default_factory=EnvelopePolicy)
    #: The file this registry was loaded from, so a drift check can name and
    #: digest the exact bytes the gate is running on rather than whichever
    #: registry happens to be on the default path.
    source: Path | None = None

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


def _flag(data: Mapping[str, Any], key: str, where: str) -> bool:
    """A boolean that must be written as one.

    `envelope_bounded: "no"` is a non-empty string and therefore truthy, which
    would silently bound a capability the author meant to leave free -- or, one
    typo later, free a capability the author meant to bound.
    """
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise RegistryError(
            f"{where}: {key!r} must be a YAML boolean, got {type(value).__name__} ({value!r})"
        )
    return value


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
            envelope_bounded=_flag(body, "envelope_bounded", cid),
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
    _assert_monotonic(bands)
    _assert_single_root(bands)

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
    _assert_non_delegable_floor(bands, capabilities, non_delegable, controls)

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

    waiver_policy = _waiver_policy(enforcement.get("waivers", {}) or {}, controls)
    envelope_policy = _envelope_policy(
        enforcement.get("envelopes", {}) or {}, authority.get("envelope_signers", ()) or ()
    )
    _assert_envelope_floor(capabilities, authority.get("envelope_required", ()) or ())

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
        waiver_policy=waiver_policy,
        envelope_policy=envelope_policy,
        source=path,
    )


def _envelope_policy(raw: Mapping[str, Any], signers: Any) -> EnvelopePolicy:
    """Bounds on the envelope path (ILR-001-DR D-01).

    `envelope_signers` is the set of principals permitted to declare an
    envelope. Leaving it out means any principal other than the one bounded may
    sign, which `neuraxis validate` reports as a warning rather than accepting
    silently: an unrestricted signer set is the weakest form the control takes,
    and it should be a decision rather than an omission.
    """
    if not isinstance(raw, Mapping):
        raise RegistryError("enforcement.envelopes must be a mapping")
    if isinstance(signers, (str, bytes)) or not isinstance(signers, (list, tuple)):
        raise RegistryError("authority.envelope_signers must be a list of principal names")
    for entry in signers:
        if not isinstance(entry, str) or not entry.strip():
            raise RegistryError(
                f"authority.envelope_signers entry {entry!r} is not a principal name"
            )
    named = frozenset(s.strip() for s in signers if s.strip())
    max_ttl = parse_duration(raw.get("max_ttl", "90d"))
    if max_ttl > MAX_ENVELOPE_TTL_CEILING:
        # Clamped rather than rejected, for the same reason the waiver bounds
        # are: a registry may tighten the ceiling and may not raise it.
        max_ttl = MAX_ENVELOPE_TTL_CEILING
    return EnvelopePolicy(signers=named, max_ttl=max_ttl)


def _waiver_policy(raw: Mapping[str, Any], controls: Mapping[str, GVControl]) -> WaiverPolicy:
    """Bounds on the exception path (ILR-001-DR D-05, D-06).

    Defaults are the ruling's own numbers. They are read from the registry
    rather than hard-coded so that widening them is a ratified registry change
    with a diff, which is the only kind of gate erosion this package is able
    to make visible.
    """
    if not isinstance(raw, Mapping):
        raise RegistryError("enforcement.waivers must be a mapping")

    listed = raw.get("non_compensable", ()) or ()
    if isinstance(listed, (str, bytes)):
        raise RegistryError("enforcement.waivers.non_compensable must be a list of control ids")
    non_compensable = frozenset(str(c).strip() for c in listed if str(c).strip())
    for cid in sorted(non_compensable):
        if cid not in controls:
            raise RegistryError(f"non_compensable references undefined control {cid}")

    max_ttl = parse_duration(raw.get("max_ttl", "90d"))

    def _bound(key: str, default: int) -> int:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            # bool is an int subclass, and `max_active: true` must not read as 1.
            raise RegistryError(
                f"enforcement.waivers.{key} must be a non-negative integer, got {value!r}"
            )
        if value < 0:
            raise RegistryError(f"enforcement.waivers.{key} must be >= 0, got {value}")
        return value

    return WaiverPolicy(
        non_compensable=non_compensable,
        max_ttl=max_ttl,
        max_active=_bound("max_active", 2),
        max_renewals=_bound("max_renewals", 1),
    )


def _assert_monotonic(bands: Mapping[str, Band]) -> None:
    """ILR-001-DR D-05: controls(band) must be a superset of every dependency's.

    A non-monotonic matrix means some transition *reduces* the controls
    required, which is unauditable and — worse — rewards declaring a higher
    band in order to escape a control. The register directs that this be
    asserted rather than assumed, so it is checked on every load rather than
    reviewed on every edit.
    """
    for band in bands.values():
        required = set(band.requires)
        for dep_id in band.depends_on:
            dep = bands[dep_id]
            dropped = sorted(set(dep.requires) - required)
            if dropped:
                raise RegistryError(
                    f"band {band.id} requires fewer controls than its prerequisite "
                    f"{dep_id}: {', '.join(dropped)} dropped. The Capability-Authority "
                    "Gate must be a monotonic staircase; a band that relaxes a control "
                    "its prerequisite demands is an incentive to claim it"
                )


def _assert_envelope_floor(
    capabilities: Mapping[str, Capability], required: Any
) -> None:
    """Every capability in `authority.envelope_required` must be envelope-bounded.

    `envelope_bounded` defaults to False, so deleting one token from a
    capability line would silently turn IL-13a into unbounded self-tuning from
    Band C -- the exact outcome ILR-001-DR D-01 exists to prevent, arriving by
    omission rather than by argument. Naming the requirement in a second place
    means the two must agree or the registry does not load, which is how the
    non-delegable floor already works.
    """
    if isinstance(required, (str, bytes)) or not isinstance(required, (list, tuple)):
        raise RegistryError("authority.envelope_required must be a list of capability ids")
    for cid in required:
        cap = capabilities.get(str(cid).strip())
        if cap is None:
            raise RegistryError(f"envelope_required references undefined capability {cid}")
        if not cap.envelope_bounded:
            raise RegistryError(
                f"{cap.id} is listed in authority.envelope_required but does not set "
                "envelope_bounded: true. A capability the gate does not check is not "
                "bounded, whatever the register says about it"
            )


def _assert_single_root(bands: Mapping[str, Band]) -> None:
    """Exactly one band may have no prerequisite.

    Monotonicity only constrains a band against the prerequisites it declares,
    so a second root is a fast lane: a band requiring one cheap control,
    depending on nothing, hosting whatever capabilities its author assigns it.
    With one root, every band inherits the root's control set transitively and
    the staircase actually reaches the ground.
    """
    roots = sorted(bid for bid, band in bands.items() if not band.depends_on)
    if len(roots) > 1:
        raise RegistryError(
            f"bands {', '.join(roots)} each declare no prerequisite. A second root "
            "band bypasses the Capability-Authority staircase entirely: it inherits "
            "no control from anything. Give it a prerequisite or fold it into one"
        )
    if not roots:
        raise RegistryError("no band is a root; every band declares a prerequisite")


def _assert_non_delegable_floor(
    bands: Mapping[str, Band],
    capabilities: Mapping[str, Capability],
    non_delegable: frozenset[str],
    controls: Mapping[str, GVControl],
) -> None:
    """A non-delegable capability's band must require every control.

    IL-31/32/33 are the capabilities ILR-001 says are never independently
    enabled. Re-homing one into a cheaper band would make it reachable under
    that band's control set -- and, once waivers exist, under a single waived
    control. Binding the floor to the full control set makes the re-homing
    fail at load rather than at the first ALLOW.
    """
    for cid in sorted(non_delegable):
        band = bands[capabilities[cid].band]
        absent = sorted(set(controls) - set(band.requires))
        if absent:
            raise RegistryError(
                f"{cid} is non-delegable but sits in {band.id}, which does not require "
                f"{', '.join(absent)}. A non-delegable capability must sit in a band "
                "that requires every governance control; otherwise the floor is only "
                "as high as the band it was moved to"
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
