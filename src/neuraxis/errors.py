"""Neuraxis error taxonomy.

Every error here is fail-closed by construction: the gate converts any
NeuraxisError into a DENY verdict rather than allowing through a fault.
"""

from __future__ import annotations


class NeuraxisError(Exception):
    """Base for all Neuraxis failures."""


class RegistryError(NeuraxisError):
    """The registry is malformed, incomplete, or internally inconsistent.

    Never recovered from with a default. A registry that cannot be validated
    is treated as absent, and an absent registry denies everything.
    """


class CycleError(RegistryError):
    """Band dependency graph contains a cycle."""


class UnknownCapabilityError(NeuraxisError):
    """A capability id was requested that the registry does not define.

    Denied rather than allowed: an unknown capability is an ungoverned one.
    """


class UnknownControlError(RegistryError):
    """A band references a governance control that is not defined."""


class AttestationError(NeuraxisError):
    """An attestation is malformed, future-dated, or otherwise untrustworthy."""


class EnvelopeError(NeuraxisError):
    """An envelope is malformed, self-signed, or not machine-evaluable.

    Refused rather than narrowed. "Bounded" is what the evaluator can check;
    an envelope carrying a constraint this package cannot decide is prose, and
    prose admits IL-13b under IL-13a's name.
    """


class WaiverError(NeuraxisError):
    """A waiver is malformed, unbounded, or waives a non-compensable control.

    Structural only. Exceeding the active-waiver cap is a policy state, not a
    malformed record: it voids the exception path rather than raising, so the
    gate keeps answering and every answer is a denial.
    """
