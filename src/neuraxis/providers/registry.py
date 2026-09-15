"""Provider registry — name to instance, and control to providers."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..errors import NeuraxisError
from .base import Provider
from .builtin import builtin_providers

PROVIDERS: dict[str, Callable[..., Provider]] = {}


class UnknownProviderError(NeuraxisError):
    """A provider name was requested that is not registered."""


def register(name: str, factory: Callable[..., Provider]) -> None:
    """Register a provider factory under its attestation name.

    Re-registering a name is rejected rather than overwriting: a silently
    replaced provider is a way to swap a real check for a permissive one.
    """
    if name in PROVIDERS:
        raise NeuraxisError(f"provider {name!r} is already registered; refusing to overwrite")
    PROVIDERS[name] = factory


def _instances(**config: Any) -> list[Provider]:
    built = builtin_providers(**config)
    extra = [factory(**config) for name, factory in PROVIDERS.items()]
    return built + extra


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
