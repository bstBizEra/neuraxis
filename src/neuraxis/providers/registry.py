"""Provider registry — name to instance, and control to providers."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..errors import NeuraxisError
from .base import Provider, UnwiredProvider
from .builtin import builtin_providers

PROVIDERS: dict[str, Callable[..., Provider]] = {}


class UnknownProviderError(NeuraxisError):
    """A provider name was requested that is not registered."""


def register(name: str, factory: Callable[..., Provider]) -> None:
    """Register a provider factory under its attestation name.

    Re-registering a name is rejected rather than overwriting: a silently
    replaced provider is a way to swap a real check for a permissive one.

    A name or control already claimed by a builtin is rejected too. Builtins
    are not in PROVIDERS, so guarding only that dict left the real check
    shadowable — and because extras run after builtins, the shadow's
    attestation carried the later timestamp and won.
    """
    if name in PROVIDERS:
        raise NeuraxisError(f"provider {name!r} is already registered; refusing to overwrite")

    try:
        claimed = factory().control
    except Exception as exc:  # noqa: BLE001
        raise NeuraxisError(f"provider {name!r} could not be constructed: {exc}") from exc

    for builtin in builtin_providers():
        if builtin.name == name:
            raise NeuraxisError(f"provider {name!r} is a builtin; refusing to shadow it")
        if builtin.control != claimed:
            continue
        if not isinstance(builtin, UnwiredProvider):
            # Replacing a wired check with an outside one is the shadowing
            # attack: extras run after builtins, so the shadow's attestation
            # carries the later timestamp and wins.
            raise NeuraxisError(
                f"control {claimed} is already covered by wired builtin "
                f"{builtin.name!r}; refusing to shadow it"
            )
    PROVIDERS[name] = factory


def _instances(**config: Any) -> list[Provider]:
    """Builtins, with any UNWIRED stub replaced by a registered real provider.

    Registering is the supported way to wire one of the controls this package
    cannot wire itself. Replacement is exact — the stub is removed rather than
    both running — so no control is ever covered twice.
    """
    extra = [factory(**config) for factory in PROVIDERS.values()]
    replaced = {p.control for p in extra}
    built = [
        p
        for p in builtin_providers(**config)
        if not (isinstance(p, UnwiredProvider) and p.control in replaced)
    ]
    instances = built + extra

    seen_names: set[str] = set()
    seen_controls: set[str] = set()
    for provider in instances:
        if provider.name in seen_names:
            raise NeuraxisError(
                f"two providers named {provider.name!r}; one is shadowing the other"
            )
        if provider.control in seen_controls:
            raise NeuraxisError(
                f"two providers claim {provider.control}; a control covered twice is "
                "a control whose result depends on ordering"
            )
        seen_names.add(provider.name)
        seen_controls.add(provider.control)
    return instances


def get_provider(name: str, **config: Any) -> Provider:
    for provider in _instances(**config):
        if provider.name == name:
            return provider
    raise UnknownProviderError(
        f"no provider named {name!r}; known: {', '.join(sorted(p.name for p in _instances()))}"
    )


def providers_for(control: str | None = None, **config: Any) -> list[Provider]:
    """Providers for one control, or all of them when control is None."""
    instances = _instances(**config)
    if control is None:
        return instances
    return [p for p in instances if p.control == control]


def coverage(controls: Mapping[str, Any], **config: Any) -> dict[str, list[str]]:
    """Which registered providers cover each control. Empty list means none."""
    instances = _instances(**config)
    return {cid: [p.name for p in instances if p.control == cid] for cid in controls}
