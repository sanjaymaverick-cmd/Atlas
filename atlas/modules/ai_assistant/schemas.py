"""Transient and published Phase 11 AI safety DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AssistantRequest:
    query: str
    intent: str
    proposed_action: str
    legal_entity_id: UUID | None = None
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    source_type: str
    source_id: UUID


@dataclass(frozen=True, slots=True)
class SafePrompt:
    system_policy: str
    user_query: str
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class ModelResult:
    text: str
    confidence: float
    evidence: tuple[EvidenceReference, ...] = ()


@dataclass(frozen=True, slots=True)
class AssistantOutcome:
    query_id: UUID
    status: str
    intent: str
    authority_level: int
    response: str | None
    confidence: float | None
    evidence: tuple[EvidenceReference, ...]
