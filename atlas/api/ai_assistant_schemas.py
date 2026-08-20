"""Validated HTTP models for the provider-neutral assistant boundary."""

from __future__ import annotations

from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.ai_assistant.schemas import AssistantRequest


class AssistantRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=12000)
    intent: str = Field(pattern="^(information|drafting|recommendation|workflow_assistance)$")
    proposed_action: str = Field(min_length=1, max_length=100)
    legal_entity_id: UUID | None = None
    project_id: UUID | None = None

    def to_dto(self) -> AssistantRequest:
        return AssistantRequest(**self.model_dump())


class EvidenceResponse(BaseModel):
    source_type: str
    source_id: UUID


class AssistantResponse(BaseModel):
    query_id: UUID
    status: str
    intent: str
    authority_level: int
    response: str | None
    confidence: float | None
    evidence: list[EvidenceResponse]

    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(
            query_id=value.query_id,
            status=value.status,
            intent=value.intent,
            authority_level=value.authority_level,
            response=value.response,
            confidence=value.confidence,
            evidence=[
                EvidenceResponse(source_type=e.source_type, source_id=e.source_id)
                for e in value.evidence
            ],
        )
