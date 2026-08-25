"""Audited Phase 3 land, legal, loan, EMI, and PDC workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.land.contracts import (
    LandConflictError,
    LandNotAuthorisedError,
    LandNotFoundError,
)
from atlas.modules.land.models import (
    DueDiligenceItem,
    LandLegalApproval,
    LandParcel,
    LoanInstallment,
    LoanObligation,
)
from atlas.modules.land.schemas import (
    DueDiligenceCreate,
    DueDiligenceSummary,
    InstallmentCreate,
    InstallmentSummary,
    LandParcelCreate,
    LandParcelSummary,
    LegalApprovalCreate,
    LegalApprovalSummary,
    LoanCreate,
    LoanSummary,
)
from atlas.platform.audit.writer import record_event

PARCEL_TRANSITIONS = {
    "identified": frozenset({"due_diligence", "dropped"}),
    "due_diligence": frozenset({"under_negotiation", "dropped"}),
    "under_negotiation": frozenset({"acquired", "dropped"}),
}
APPROVAL_TRANSITIONS = {
    "pending": frozenset({"applied"}),
    "applied": frozenset({"approved", "rejected"}),
    "approved": frozenset({"expired"}),
}
INSTALLMENT_TRANSITIONS = {
    "scheduled": frozenset({"paid", "bounced", "waived", "overdue"}),
    "bounced": frozenset({"scheduled", "paid", "waived"}),
    "overdue": frozenset({"paid", "waived"}),
}
LOAN_TRANSITIONS = {"active": frozenset({"closed", "defaulted"})}


def parcel_summary(row: LandParcel) -> LandParcelSummary:
    return LandParcelSummary(
        row.id,
        row.legal_entity_id,
        row.project_id,
        row.survey_number,
        row.area_sqft,
        row.location,
        row.acquisition_status,
        row.status,
        row.version,
        row.archived_at,
    )


def diligence_summary(row: DueDiligenceItem) -> DueDiligenceSummary:
    return DueDiligenceSummary(
        row.id,
        row.land_parcel_id,
        row.category,
        row.title,
        row.result,
        row.evidence_document_id,
        row.notes,
        row.version,
        row.archived_at,
    )


def approval_summary(row: LandLegalApproval) -> LegalApprovalSummary:
    return LegalApprovalSummary(
        row.id,
        row.land_parcel_id,
        row.project_id,
        row.approval_type,
        row.authority,
        row.reference_number,
        row.valid_from,
        row.valid_to,
        row.status,
        row.version,
        row.archived_at,
    )


def loan_summary(row: LoanObligation) -> LoanSummary:
    return LoanSummary(
        row.id,
        row.legal_entity_id,
        row.project_id,
        row.lender_name,
        row.principal_amount,
        row.emi_amount,
        row.emi_due_day,
        row.status,
        row.version,
        row.archived_at,
    )


def installment_summary(row: LoanInstallment) -> InstallmentSummary:
    return InstallmentSummary(
        row.id,
        row.loan_obligation_id,
        row.due_date,
        row.amount,
        row.instrument_type,
        row.reference_number,
        row.status,
        row.paid_at,
        row.version,
        row.archived_at,
    )


def auditable(row: Any, *fields: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        value = getattr(row, field, None)
        if value is not None:
            result[field] = str(value) if isinstance(value, UUID) else value
    return result


class LandService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        permission: str,
        legal_entity_id: UUID | None,
        project_id: UUID | None,
    ) -> None:
        if not await self._identity.check_scoped_role(
            session,
            user_id=actor_user_id,
            permission_code=permission,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
        ):
            raise LandNotAuthorisedError(f"user may not {permission} in the requested scope")

    async def _parcel(
        self, session: AsyncSession, *, actor_user_id: UUID, parcel_id: UUID, permission: str
    ) -> LandParcel:
        row = await session.get(LandParcel, parcel_id)
        if row is None:
            raise LandNotFoundError(f"land parcel {parcel_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=permission,
            legal_entity_id=row.legal_entity_id,
            project_id=row.project_id,
        )
        return row

    async def create_parcel(
        self, session: AsyncSession, *, actor_user_id: UUID, data: LandParcelCreate
    ) -> LandParcelSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="land.create",
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = LandParcel(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
            survey_number=data.survey_number,
            area_sqft=data.area_sqft,
            location=data.location,
            acquisition_status="identified",
            status="active",
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
            entity_schema="land",
            entity_table="land_parcels",
            entity_id=row.id,
            action="create",
            after_state=auditable(
                row,
                "legal_entity_id",
                "project_id",
                "survey_number",
                "area_sqft",
                "acquisition_status",
                "version",
            ),
        )
        return parcel_summary(row)

    async def list_parcels(
        self, session: AsyncSession, *, actor_user_id: UUID, legal_entity_id: UUID
    ) -> list[LandParcelSummary]:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="land.read",
            legal_entity_id=legal_entity_id,
            project_id=None,
        )
        result = await session.execute(
            select(LandParcel)
            .where(LandParcel.legal_entity_id == legal_entity_id)
            .where(LandParcel.archived_at.is_(None))
            .order_by(LandParcel.created_at)
        )
        return [parcel_summary(row) for row in result.scalars()]

    async def transition_parcel(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        target_status: str,
    ) -> LandParcelSummary:
        row = await self._parcel(
            session,
            actor_user_id=actor_user_id,
            parcel_id=parcel_id,
            permission="land.update",
        )
        if target_status not in PARCEL_TRANSITIONS.get(row.acquisition_status, frozenset()):
            raise LandConflictError(
                f"parcel cannot move from {row.acquisition_status} to {target_status}"
            )
        before = {"acquisition_status": row.acquisition_status, "version": row.version}
        row.acquisition_status = target_status
        row.version += 1
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="land_parcels",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={"acquisition_status": target_status, "version": row.version},
        )
        return parcel_summary(row)

    async def add_due_diligence(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        data: DueDiligenceCreate,
    ) -> DueDiligenceSummary:
        parcel = await self._parcel(
            session,
            actor_user_id=actor_user_id,
            parcel_id=parcel_id,
            permission="land.due_diligence.manage",
        )
        now = datetime.now(UTC)
        row = DueDiligenceItem(
            id=uuid4(),
            land_parcel_id=parcel.id,
            category=data.category,
            title=data.title,
            result="pending",
            evidence_document_id=data.evidence_document_id,
            notes=data.notes,
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
            entity_schema="land",
            entity_table="due_diligence_items",
            entity_id=row.id,
            action="create",
            after_state=auditable(row, "land_parcel_id", "category", "title", "result"),
        )
        return diligence_summary(row)

    async def resolve_due_diligence(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        item_id: UUID,
        result: str,
        notes: str | None,
    ) -> DueDiligenceSummary:
        row = await session.get(DueDiligenceItem, item_id)
        if row is None:
            raise LandNotFoundError(f"due diligence item {item_id} does not exist")
        await self._parcel(
            session,
            actor_user_id=actor_user_id,
            parcel_id=row.land_parcel_id,
            permission="land.due_diligence.manage",
        )
        if row.result != "pending" or result not in {"clear", "issue", "waived"}:
            raise LandConflictError("due diligence result is final or invalid")
        before = {"result": row.result, "notes": row.notes, "version": row.version}
        row.result = result
        row.notes = notes
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="due_diligence_items",
            entity_id=row.id,
            action="resolve",
            before_state=before,
            after_state={"result": row.result, "notes": row.notes, "version": row.version},
        )
        return diligence_summary(row)

    async def add_legal_approval(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        parcel_id: UUID,
        data: LegalApprovalCreate,
    ) -> LegalApprovalSummary:
        parcel = await self._parcel(
            session,
            actor_user_id=actor_user_id,
            parcel_id=parcel_id,
            permission="land.approval.manage",
        )
        now = datetime.now(UTC)
        row = LandLegalApproval(
            id=uuid4(),
            land_parcel_id=parcel.id,
            project_id=parcel.project_id,
            approval_type=data.approval_type,
            authority=data.authority,
            reference_number=data.reference_number,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            status="pending",
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
            entity_schema="land",
            entity_table="land_legal_approvals",
            entity_id=row.id,
            action="create",
            after_state=auditable(
                row,
                "land_parcel_id",
                "project_id",
                "approval_type",
                "authority",
                "reference_number",
                "status",
                "version",
            ),
        )
        return approval_summary(row)

    async def transition_legal_approval(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        approval_id: UUID,
        target_status: str,
    ) -> LegalApprovalSummary:
        row = await session.get(LandLegalApproval, approval_id)
        if row is None or row.land_parcel_id is None:
            raise LandNotFoundError(f"legal approval {approval_id} does not exist")
        await self._parcel(
            session,
            actor_user_id=actor_user_id,
            parcel_id=row.land_parcel_id,
            permission="land.approval.manage",
        )
        if target_status not in APPROVAL_TRANSITIONS.get(row.status, frozenset()):
            raise LandConflictError(f"approval cannot move from {row.status} to {target_status}")
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="land_legal_approvals",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={"status": row.status, "version": row.version},
        )
        return approval_summary(row)

    async def create_loan(
        self, session: AsyncSession, *, actor_user_id: UUID, data: LoanCreate
    ) -> LoanSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="land.loan.manage",
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
        )
        if data.emi_due_day is not None and not 1 <= data.emi_due_day <= 31:
            raise LandConflictError("EMI due day must be between 1 and 31")
        now = datetime.now(UTC)
        row = LoanObligation(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
            lender_name=data.lender_name,
            principal_amount=data.principal_amount,
            emi_amount=data.emi_amount,
            emi_due_day=data.emi_due_day,
            status="active",
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
            entity_schema="land",
            entity_table="loan_obligations",
            entity_id=row.id,
            action="create",
            after_state=auditable(
                row,
                "legal_entity_id",
                "project_id",
                "lender_name",
                "principal_amount",
                "emi_amount",
                "emi_due_day",
                "status",
                "version",
            ),
        )
        return loan_summary(row)

    async def _loan(
        self, session: AsyncSession, *, actor_user_id: UUID, loan_id: UUID
    ) -> LoanObligation:
        row = await session.get(LoanObligation, loan_id)
        if row is None:
            raise LandNotFoundError(f"loan {loan_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="land.loan.manage",
            legal_entity_id=row.legal_entity_id,
            project_id=row.project_id,
        )
        return row

    async def add_installment(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        loan_id: UUID,
        data: InstallmentCreate,
    ) -> InstallmentSummary:
        loan = await self._loan(session, actor_user_id=actor_user_id, loan_id=loan_id)
        if loan.status != "active":
            raise LandConflictError("installments may only be added to an active loan")
        if data.amount < 0:
            raise LandConflictError("installment amount must not be negative")
        now = datetime.now(UTC)
        row = LoanInstallment(
            id=uuid4(),
            loan_obligation_id=loan.id,
            due_date=data.due_date,
            amount=data.amount,
            instrument_type=data.instrument_type,
            reference_number=data.reference_number,
            status="scheduled",
            paid_at=None,
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
            raise LandConflictError("an installment already exists for this date and type") from exc
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="loan_installments",
            entity_id=row.id,
            action="create",
            after_state=auditable(
                row,
                "loan_obligation_id",
                "due_date",
                "amount",
                "instrument_type",
                "reference_number",
                "status",
                "version",
            ),
        )
        return installment_summary(row)

    async def transition_installment(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        installment_id: UUID,
        target_status: str,
    ) -> InstallmentSummary:
        row = await session.get(LoanInstallment, installment_id)
        if row is None:
            raise LandNotFoundError(f"installment {installment_id} does not exist")
        await self._loan(
            session,
            actor_user_id=actor_user_id,
            loan_id=row.loan_obligation_id,
        )
        if target_status not in INSTALLMENT_TRANSITIONS.get(row.status, frozenset()):
            raise LandConflictError(f"installment cannot move from {row.status} to {target_status}")
        before = {"status": row.status, "paid_at": row.paid_at, "version": row.version}
        row.status = target_status
        row.paid_at = datetime.now(UTC) if target_status == "paid" else None
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="loan_installments",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={
                "status": row.status,
                "paid_at": row.paid_at,
                "version": row.version,
            },
        )
        return installment_summary(row)

    async def transition_loan(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        loan_id: UUID,
        target_status: str,
    ) -> LoanSummary:
        row = await self._loan(session, actor_user_id=actor_user_id, loan_id=loan_id)
        if target_status not in LOAN_TRANSITIONS.get(row.status, frozenset()):
            raise LandConflictError(f"loan cannot move from {row.status} to {target_status}")
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="land",
            entity_table="loan_obligations",
            entity_id=row.id,
            action="transition",
            before_state=before,
            after_state={"status": row.status, "version": row.version},
        )
        return loan_summary(row)
