"""BST Neuraxis — Intelligent Loop Registry and Governance Gate (ILR-001).

Principle: Governed Evolution. Capability is licensed by the governance
controls paired to it, enforced mechanically rather than by instruction.

    from neuraxis import load_registry, AttestationStore, GovernanceGate
    from neuraxis import AuthorityRequest, Risk

    gate = GovernanceGate(load_registry(), AttestationStore.from_file("attestations.jsonl"))
    verdict = gate.evaluate(AuthorityRequest(
        intent="promote lesson to canonical",
        identity="agent-cortex", role="cortex", capability="IL-11",
        scope="hippocampus/lessons", verifier="ci-runner",
    ))
    if verdict.permits_action:
        ...
"""

from __future__ import annotations

from .attestation import AttestationStore
from .errors import (
    AttestationError,
    CycleError,
    NeuraxisError,
    RegistryError,
    UnknownCapabilityError,
    UnknownControlError,
    WaiverError,
)
from .evidence import (
    DischargeRecord,
    EvidenceError,
    EvidenceRecord,
    EvidenceSink,
    ObligationAudit,
    OutstandingObligation,
    audit_obligations,
    record_decision,
)
from .gate import GovernanceGate
from .guard import CapabilityDenied, CapabilityGuard
from .model import (
    Attestation,
    AuthorityRequest,
    Band,
    BandStatus,
    Capability,
    Decision,
    GVControl,
    Obligation,
    Risk,
    Verdict,
)
from .providers import (
    Provider,
    ProviderOutcome,
    ProviderResult,
    UnwiredProvider,
    get_provider,
    providers_for,
    run_provider,
)
from .registry import Registry, load_registry
from .resolver import BandResolver
from .scorecard import Scorecard, measure
from .waiver import Waiver, WaiverPolicy, WaiverRegister

__version__ = "0.8.0"
FRAMEWORK = "bst-neuraxis"
PRINCIPLE = "governed-evolution"

__all__ = [
    "Attestation",
    "AttestationError",
    "AttestationStore",
    "AuthorityRequest",
    "Band",
    "BandResolver",
    "BandStatus",
    "Capability",
    "CapabilityDenied",
    "CapabilityGuard",
    "CycleError",
    "Decision",
    "DischargeRecord",
    "EvidenceError",
    "EvidenceRecord",
    "EvidenceSink",
    "FRAMEWORK",
    "GVControl",
    "GovernanceGate",
    "NeuraxisError",
    "Obligation",
    "ObligationAudit",
    "OutstandingObligation",
    "PRINCIPLE",
    "Provider",
    "ProviderOutcome",
    "ProviderResult",
    "Registry",
    "RegistryError",
    "Risk",
    "Scorecard",
    "UnknownCapabilityError",
    "UnknownControlError",
    "UnwiredProvider",
    "Verdict",
    "Waiver",
    "WaiverError",
    "WaiverPolicy",
    "WaiverRegister",
    "__version__",
    "audit_obligations",
    "get_provider",
    "load_registry",
    "measure",
    "providers_for",
    "record_decision",
    "run_provider",
]
