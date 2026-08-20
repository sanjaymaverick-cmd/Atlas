"""Audited statutory registration and obligation workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.compliance.contracts import (
    ComplianceConflictError,
    ComplianceNotAuthorisedError,
    ComplianceNotFoundError,
)
from atlas.modules.compliance.models import ComplianceObligation, ReraRegistration
from atlas.modules.compliance.schemas import (
    ComplianceObligationCreate,
    ComplianceObligationSummary,
    ReraRegistrationCreate,
    ReraRegistrationSummary,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

REGISTRATION_TRANSITIONS = {"active": frozenset({"lapsed", "revoked"})}
OBLIGATION_TRANSITIONS = {
    "open": frozenset({"paid", "waived", "overdue"}),
    "overdue": frozenset({"paid", "waived"}),
}


def registration_summary(row: ReraRegistration) -> ReraRegistrationSummary:
    return ReraRegistrationSummary(
        row.id,
        row.project_id,
        row.registration_number,
        row.valid_from,
        row.valid_to,
        row.status,
        row.version,
        row.archived_at,
    )


def obligation_summary(row: ComplianceObligation) -> ComplianceObligationSummary:
    return ComplianceObligationSummary(
        row.id,
        row.legal_entity_id,
        row.project_id,
        row.obligation_type,
        row.authority,
        row.due_date,
        row.amount,
        row.status,
        row.version,
        row.archived_at,
    )


PERM_READ = "compliance.read"


class ComplianceService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        permission: str,
        legal_entity_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> None:
        allowed = await self._identity.check_scoped_role(
            session,
            user_id=actor_user_id,
            permission_code=permission,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
        )
        if not allowed:
            raise ComplianceNotAuthorisedError(f"user may not {permission} in the requested scope")

    async def create_registration(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ReraRegistrationCreate
    ) -> ReraRegistrationSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="compliance.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = ReraRegistration(
            id=uuid4(),
            project_id=data.project_id,
            registration_number=data.registration_number,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            status="active",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ComplianceConflictError("registration number already exists") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="compliance",
            entity_table="rera_registrations",
            entity_id=row.id,
            action="create",
            after_state={
                "project_id": str(row.project_id),
                "registration_number": row.registration_number,
                "status": row.status,
                "version": row.version,
            },
        )
        return registration_summary(row)

    async def transition_registration(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        registration_id: UUID,
        target_status: str,
    ) -> ReraRegistrationSummary:
        row = await session.get(ReraRegistration, registration_id)
        if row is None:
            raise ComplianceNotFoundError(f"registration {registration_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="compliance.update",
            project_id=row.project_id,
        )
        if target_status not in REGISTRATION_TRANSITIONS.get(row.status, frozenset()):
            raise ComplianceConflictError(
                f"registration cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        row.status, row.updated_at, row.updated_by, row.version = (
            target_status,
            datetime.now(UTC),
            actor_user_id,
            row.version + 1,
        )
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="compliance",
            entity_table="rera_registrations",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={"status": row.status, "version": row.version},
        )
        return registration_summary(row)

    async def create_obligation(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ComplianceObligationCreate
    ) -> ComplianceObligationSummary:
        if data.legal_entity_id is None and data.project_id is None:
            raise ComplianceConflictError("an obligation requires a legal entity or project scope")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="compliance.create",
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = ComplianceObligation(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
            obligation_type=data.obligation_type,
            authority=data.authority,
            due_date=data.due_date,
            amount=data.amount,
            status="open",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="compliance",
            entity_table="compliance_obligations",
            entity_id=row.id,
            action="create",
            after_state={
                "legal_entity_id": str(row.legal_entity_id) if row.legal_entity_id else None,
                "project_id": str(row.project_id) if row.project_id else None,
                "obligation_type": row.obligation_type,
                "status": row.status,
                "version": row.version,
            },
        )
        return obligation_summary(row)

    async def transition_obligation(
        self, session: AsyncSession, *, actor_user_id: UUID, obligation_id: UUID, target_status: str
    ) -> ComplianceObligationSummary:
        row = await session.get(ComplianceObligation, obligation_id)
        if row is None:
            raise ComplianceNotFoundError(f"obligation {obligation_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="compliance.update",
            legal_entity_id=row.legal_entity_id,
            project_id=row.project_id,
        )
        if target_status not in OBLIGATION_TRANSITIONS.get(row.status, frozenset()):
            raise ComplianceConflictError(
                f"obligation cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        row.status, row.updated_at, row.updated_by, row.version = (
            target_status,
            datetime.now(UTC),
            actor_user_id,
            row.version + 1,
        )
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="compliance",
            entity_table="compliance_obligations",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={"status": row.status, "version": row.version},
        )
        return obligation_summary(row)

    # -- reads ------------------------------------------------------------
    # Added 2026-08-20; this module previously published writes only.

    async def list_registrations(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ReraRegistrationSummary]:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_READ,
            project_id=project_id,
        )
        result = await session.execute(
            select(ReraRegistration)
            .where(ReraRegistration.project_id == project_id)
            .where(ReraRegistration.archived_at.is_(None))
            .order_by(ReraRegistration.created_at)
        )
        return [registration_summary(row) for row in result.scalars()]

    async def list_obligations(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ComplianceObligationSummary]:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_READ,
            project_id=project_id,
        )
        result = await session.execute(
            select(ComplianceObligation)
            .where(ComplianceObligation.project_id == project_id)
            .where(ComplianceObligation.archived_at.is_(None))
            .order_by(ComplianceObligation.created_at)
        )
        return [obligation_summary(row) for row in result.scalars()]
