"""Fail-closed provider-neutral Phase 11 assistant service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.ai_assistant.contracts import AssistantConflictError, AssistantNotAuthorisedError
from atlas.modules.ai_assistant.models import AiQuery, AuthorityLog
from atlas.modules.ai_assistant.policy import SYSTEM_POLICY, evaluate
from atlas.modules.ai_assistant.provider import (
    DisabledInferenceProvider,
    HostingNotConfiguredError,
    InferenceProvider,
)
from atlas.modules.ai_assistant.schemas import (
    AssistantOutcome,
    AssistantRequest,
    ModelResult,
    SafePrompt,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

MAX_QUERY_LENGTH = 12_000
MIN_CONFIDENCE = 0.80


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class AssistantService:
    def __init__(
        self,
        identity: IdentityContract,
        provider: InferenceProvider | None = None,
        *,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        if not 0 < min_confidence <= 1:
            raise ValueError("minimum confidence must be in (0, 1]")
        self._identity = identity
        self._provider = provider or DisabledInferenceProvider()
        self._min_confidence = min_confidence

    async def _authorise(self, s: AsyncSession, actor: UUID, request: AssistantRequest) -> None:
        if not await self._identity.check_scoped_role(
            s,
            user_id=actor,
            permission_code="ai.assistant.use",
            legal_entity_id=request.legal_entity_id,
            project_id=request.project_id,
        ):
            raise AssistantNotAuthorisedError("user may not use assistant in requested scope")

    async def ask(
        self, s: AsyncSession, *, actor_user_id: UUID, request: AssistantRequest
    ) -> AssistantOutcome:
        await self._authorise(s, actor_user_id, request)
        query = request.query.strip()
        if not query or len(query) > MAX_QUERY_LENGTH:
            raise AssistantConflictError("query length is outside the allowed range")
        decision = evaluate(request.intent, request.proposed_action, query)
        result: ModelResult | None = None
        status: str
        reason = decision.reason_code
        if not decision.allowed:
            status = (
                "blocked_prompt_injection"
                if reason == "prompt_injection_signal"
                else "blocked_authority"
            )
        else:
            try:
                result = await self._provider.generate(SafePrompt(SYSTEM_POLICY, query, ()))
            except HostingNotConfiguredError:
                status = "hosting_not_configured"
                reason = "hosting_not_configured"
            else:
                if not 0 <= result.confidence <= 1:
                    raise AssistantConflictError("provider returned invalid confidence")
                status = (
                    "answered"
                    if result.confidence >= self._min_confidence
                    else "declined_low_confidence"
                )
                reason = "confidence_met" if status == "answered" else "low_confidence"
        now = datetime.now(UTC)
        response_text = result.text if result is not None else None
        confidence = result.confidence if result is not None else None
        row = AiQuery(
            id=uuid4(),
            user_id=actor_user_id,
            legal_entity_id=request.legal_entity_id,
            project_id=request.project_id,
            request_digest=digest(query),
            request_length=len(query),
            intent_classification=request.intent,
            authority_level=decision.authority_level,
            response_digest=digest(response_text) if response_text is not None else None,
            response_length=len(response_text) if response_text is not None else None,
            confidence=Decimal(str(confidence)) if confidence is not None else None,
            required_approver=None,
            status=status,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        authority = AuthorityLog(
            id=uuid4(),
            ai_query_id=row.id,
            authority_level=decision.authority_level,
            action_code=request.proposed_action,
            blocked=status != "answered",
            reason_code=reason,
            created_at=now,
        )
        s.add_all([row, authority])
        await s.flush()
        safe_state = {
            "legal_entity_id": str(row.legal_entity_id) if row.legal_entity_id else None,
            "project_id": str(row.project_id) if row.project_id else None,
            "intent": row.intent_classification,
            "authority_level": row.authority_level,
            "action_code": authority.action_code,
            "request_length": row.request_length,
            "request_digest_recorded": True,
            "response_length": row.response_length,
            "response_digest_recorded": row.response_digest is not None,
            "confidence": str(row.confidence) if row.confidence is not None else None,
            "status": row.status,
            "reason_code": reason,
            "version": 1,
        }
        await record_event(
            s,
            actor_user_id=actor_user_id,
            entity_schema="ai",
            entity_table="ai_queries",
            entity_id=row.id,
            action="evaluate",
            before_state=None,
            after_state=safe_state,
        )
        returned = response_text if status == "answered" else None
        return AssistantOutcome(
            row.id,
            status,
            request.intent,
            decision.authority_level,
            returned,
            confidence,
            result.evidence if result is not None and status == "answered" else (),
        )
