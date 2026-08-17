"""Audited Phase 8 customer-lifecycle workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.commercial.contracts import CommercialContract
from atlas.modules.customer_lifecycle.contracts import (
    CustomerLifecycleConflictError,
    CustomerLifecycleNotAuthorisedError,
    CustomerLifecycleNotFoundError,
)
from atlas.modules.customer_lifecycle.models import (
    Booking,
    BookingContract,
    Collection,
    Installment,
    PaymentPlan,
    Possession,
    Registration,
)
from atlas.modules.customer_lifecycle.schemas import (
    BookingContractSummary,
    BookingCreate,
    BookingSummary,
    CollectionCreate,
    CollectionSummary,
    InstallmentCreate,
    InstallmentSummary,
    PlanCreate,
    PlanSummary,
    PossessionSummary,
    PossessionTransition,
    RegistrationSummary,
    RegistrationTransition,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.organization.contracts import OrganizationContract
from atlas.platform.audit.writer import record_event

REG_TRANSITIONS = {
    "pending": frozenset({"scheduled", "cancelled"}),
    "scheduled": frozenset({"registered", "cancelled"}),
}
POS_TRANSITIONS = {"pending": frozenset({"snag_review"}), "snag_review": frozenset({"handed_over"})}


def booking_summary(r: Booking) -> BookingSummary:
    return BookingSummary(
        r.id,
        r.project_id,
        r.customer_id,
        r.unit_id,
        r.booking_date,
        r.booking_document_id,
        r.status,
        r.version,
    )


def plan_summary(r: PaymentPlan) -> PlanSummary:
    return PlanSummary(r.id, r.booking_id, r.plan_name, r.total_amount, r.status, r.version)


def installment_summary(r: Installment) -> InstallmentSummary:
    return InstallmentSummary(r.id, r.payment_plan_id, r.due_date, r.amount, r.status, r.version)


def collection_summary(r: Collection) -> CollectionSummary:
    return CollectionSummary(
        r.id,
        r.booking_id,
        r.installment_id,
        r.amount,
        r.received_date,
        r.status,
        r.evidence_document_id,
        r.version,
    )


def registration_summary(r: Registration) -> RegistrationSummary:
    return RegistrationSummary(
        r.id,
        r.booking_id,
        r.registration_date,
        r.status,
        r.evidence_document_id,
        r.registered_by,
        r.version,
    )


def possession_summary(r: Possession) -> PossessionSummary:
    return PossessionSummary(
        r.id,
        r.booking_id,
        r.handover_date,
        r.status,
        r.evidence_document_id,
        r.handed_over_by,
        r.version,
    )


def contract_summary(r: BookingContract) -> BookingContractSummary:
    return BookingContractSummary(
        r.id,
        r.booking_id,
        r.contract_id,
        r.executed_document_id,
        r.linked_at,
        r.linked_by,
        r.version,
    )


class CustomerLifecycleService:
    def __init__(
        self,
        identity: IdentityContract,
        organization: OrganizationContract,
        commercial: CommercialContract,
    ) -> None:
        self._identity = identity
        self._organization = organization
        self._commercial = commercial

    async def _require(self, s: AsyncSession, actor: UUID, permission: str, project: UUID) -> None:
        if not await self._identity.check_scoped_role(
            s, user_id=actor, permission_code=permission, project_id=project
        ):
            raise CustomerLifecycleNotAuthorisedError(
                f"user may not {permission} in requested scope"
            )

    async def _audit(
        self,
        s: AsyncSession,
        actor: UUID,
        table: str,
        row: UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
    ) -> None:
        await record_event(
            s,
            actor_user_id=actor,
            entity_schema="customers",
            entity_table=table,
            entity_id=row,
            action=action,
            before_state=before,
            after_state=after,
        )

    async def _booking(self, s: AsyncSession, booking_id: UUID) -> Booking:
        row = await s.get(Booking, booking_id)
        if row is None or row.archived_at is not None:
            raise CustomerLifecycleNotFoundError(f"booking {booking_id} does not exist")
        return row

    async def create_booking(
        self, s: AsyncSession, *, actor_user_id: UUID, data: BookingCreate
    ) -> BookingSummary:
        await self._require(s, actor_user_id, "customer.booking.create", data.project_id)
        if not await self._organization.unit_belongs_to_project(
            s, unit_id=data.unit_id, project_id=data.project_id
        ):
            raise CustomerLifecycleConflictError("unit must belong to booking project")
        now = datetime.now(UTC)
        row = Booking(
            id=uuid4(),
            customer_id=data.customer_id,
            unit_id=data.unit_id,
            project_id=data.project_id,
            lead_id=data.lead_id,
            booking_date=data.booking_date,
            booking_document_id=data.booking_document_id,
            status="booked",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise CustomerLifecycleConflictError("unit already has an active booking") from exc
        await self._audit(
            s,
            actor_user_id,
            "bookings",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "customer_id": str(row.customer_id),
                "unit_id": str(row.unit_id),
                "booking_date": row.booking_date,
                "booking_document_id": str(row.booking_document_id)
                if row.booking_document_id
                else None,
                "status": "booked",
                "version": 1,
            },
        )
        return booking_summary(row)

    async def cancel_booking(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID
    ) -> BookingSummary:
        row = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.booking.cancel", row.project_id)
        if row.status != "booked":
            raise CustomerLifecycleConflictError("only a booked record may be cancelled")
        before = {"status": row.status, "version": row.version}
        row.status = "cancelled"
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "bookings",
            row.id,
            "cancel",
            before,
            {"status": "cancelled", "version": row.version},
        )
        return booking_summary(row)

    async def create_plan(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: PlanCreate
    ) -> PlanSummary:
        booking = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.plan.create", booking.project_id)
        if booking.status == "cancelled" or data.total_amount < 0:
            raise CustomerLifecycleConflictError("payment plan is invalid for this booking")
        now = datetime.now(UTC)
        row = PaymentPlan(
            id=uuid4(),
            booking_id=booking.id,
            plan_name=data.plan_name,
            total_amount=data.total_amount,
            status="active",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "payment_plans",
            row.id,
            "create",
            None,
            {
                "booking_id": str(row.booking_id),
                "total_amount": str(row.total_amount),
                "status": "active",
                "version": 1,
            },
        )
        return plan_summary(row)

    async def add_installment(
        self, s: AsyncSession, *, actor_user_id: UUID, plan_id: UUID, data: InstallmentCreate
    ) -> InstallmentSummary:
        plan = await s.get(PaymentPlan, plan_id)
        if plan is None or plan.archived_at is not None:
            raise CustomerLifecycleNotFoundError(f"payment plan {plan_id} does not exist")
        booking = await self._booking(s, plan.booking_id)
        await self._require(s, actor_user_id, "customer.plan.update", booking.project_id)
        if plan.status != "active" or data.amount <= 0:
            raise CustomerLifecycleConflictError("installment cannot be added")
        existing = await s.scalar(
            select(func.coalesce(func.sum(Installment.amount), 0)).where(
                Installment.payment_plan_id == plan.id, Installment.archived_at.is_(None)
            )
        )
        if Decimal(existing or 0) + data.amount > Decimal(plan.total_amount or 0):
            raise CustomerLifecycleConflictError("installments exceed payment plan total")
        now = datetime.now(UTC)
        row = Installment(
            id=uuid4(),
            payment_plan_id=plan.id,
            due_date=data.due_date,
            amount=data.amount,
            status="pending",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "payment_plan_installments",
            row.id,
            "create",
            None,
            {
                "payment_plan_id": str(row.payment_plan_id),
                "due_date": row.due_date,
                "amount": str(row.amount),
                "status": "pending",
                "version": 1,
            },
        )
        return installment_summary(row)

    async def record_collection(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: CollectionCreate
    ) -> CollectionSummary:
        booking = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.collection.record", booking.project_id)
        if booking.status == "cancelled" or data.amount <= 0:
            raise CustomerLifecycleConflictError("collection cannot be recorded")
        now = datetime.now(UTC)
        row = Collection(
            id=uuid4(),
            booking_id=booking.id,
            installment_id=data.installment_id,
            amount=data.amount,
            received_date=data.received_date,
            mode=data.mode,
            reference_number=data.reference_number,
            evidence_document_id=data.evidence_document_id,
            received_by=actor_user_id,
            allocated_at=None,
            status="received",
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "collections",
            row.id,
            "create",
            None,
            {
                "booking_id": str(row.booking_id),
                "installment_id": str(row.installment_id) if row.installment_id else None,
                "amount": str(row.amount),
                "received_date": row.received_date,
                "mode": row.mode,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "reference_recorded": row.reference_number is not None,
                "status": "received",
                "version": 1,
            },
        )
        return collection_summary(row)

    async def allocate_collection(
        self, s: AsyncSession, *, actor_user_id: UUID, collection_id: UUID
    ) -> CollectionSummary:
        row = await s.scalar(
            select(Collection).where(Collection.id == collection_id).with_for_update()
        )
        if row is None or row.archived_at is not None:
            raise CustomerLifecycleNotFoundError(f"collection {collection_id} does not exist")
        booking = await self._booking(s, row.booking_id)
        await self._require(s, actor_user_id, "customer.collection.allocate", booking.project_id)
        if row.status != "received" or row.installment_id is None:
            raise CustomerLifecycleConflictError("collection requires a target installment")
        installment = await s.scalar(
            select(Installment).where(Installment.id == row.installment_id).with_for_update()
        )
        if installment is None:
            raise CustomerLifecycleConflictError("target installment does not exist")
        plan = await s.get(PaymentPlan, installment.payment_plan_id)
        if plan is None or plan.booking_id != booking.id:
            raise CustomerLifecycleConflictError("installment does not belong to booking")
        allocated = await s.scalar(
            select(func.coalesce(func.sum(Collection.amount), 0)).where(
                Collection.installment_id == installment.id,
                Collection.status == "allocated",
                Collection.archived_at.is_(None),
            )
        )
        if Decimal(allocated or 0) + row.amount > Decimal(installment.amount or 0):
            raise CustomerLifecycleConflictError("allocation exceeds installment amount")
        before = {"status": row.status, "version": row.version}
        row.status = "allocated"
        row.allocated_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        installment_before: dict[str, Any] | None = None
        if Decimal(allocated or 0) + row.amount == Decimal(installment.amount or 0):
            installment_before = {"status": installment.status, "version": installment.version}
            installment.status = "collected"
            installment.updated_at = datetime.now(UTC)
            installment.updated_by = actor_user_id
            installment.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "collections",
            row.id,
            "allocate",
            before,
            {
                "installment_id": str(row.installment_id),
                "amount": str(row.amount),
                "status": "allocated",
                "version": row.version,
            },
        )
        if installment_before is not None:
            await self._audit(
                s,
                actor_user_id,
                "payment_plan_installments",
                installment.id,
                "collect",
                installment_before,
                {"status": "collected", "version": installment.version},
            )
        return collection_summary(row)

    async def transition_registration(
        self,
        s: AsyncSession,
        *,
        actor_user_id: UUID,
        booking_id: UUID,
        data: RegistrationTransition,
    ) -> RegistrationSummary:
        booking = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.registration.update", booking.project_id)
        row = await s.scalar(
            select(Registration).where(
                Registration.booking_id == booking.id, Registration.archived_at.is_(None)
            )
        )
        if row is None:
            now = datetime.now(UTC)
            row = Registration(
                id=uuid4(),
                booking_id=booking.id,
                registration_date=None,
                evidence_document_id=None,
                registered_by=None,
                status="pending",
                created_at=now,
                updated_at=now,
                created_by=actor_user_id,
                updated_by=actor_user_id,
                version=1,
                archived_at=None,
            )
            s.add(row)
            await s.flush()
        if data.target_status not in REG_TRANSITIONS.get(row.status, frozenset()):
            raise CustomerLifecycleConflictError(
                f"registration cannot move from {row.status} to {data.target_status}"
            )
        if data.target_status == "registered" and (
            data.registration_date is None or data.evidence_document_id is None
        ):
            raise CustomerLifecycleConflictError(
                "registration requires date and controlled evidence"
            )
        before = {"status": row.status, "version": row.version}
        row.status = data.target_status
        if data.registration_date:
            row.registration_date = data.registration_date
        if data.evidence_document_id:
            row.evidence_document_id = data.evidence_document_id
        booking_before: dict[str, Any] | None = None
        if data.target_status == "registered":
            row.registered_by = actor_user_id
            booking_before = {"status": booking.status, "version": booking.version}
            booking.status = "registered"
            booking.updated_at = datetime.now(UTC)
            booking.updated_by = actor_user_id
            booking.version += 1
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "registration_records",
            row.id,
            "transition",
            before,
            {
                "booking_id": str(row.booking_id),
                "status": row.status,
                "registration_date": row.registration_date,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "registered_by": str(row.registered_by) if row.registered_by else None,
                "version": row.version,
            },
        )
        if booking_before is not None:
            await self._audit(
                s,
                actor_user_id,
                "bookings",
                booking.id,
                "register",
                booking_before,
                {"status": booking.status, "version": booking.version},
            )
        return registration_summary(row)

    async def transition_possession(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, data: PossessionTransition
    ) -> PossessionSummary:
        booking = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.possession.update", booking.project_id)
        if booking.status not in {"registered", "possessed"}:
            raise CustomerLifecycleConflictError("booking must be registered before possession")
        row = await s.scalar(
            select(Possession).where(
                Possession.booking_id == booking.id, Possession.archived_at.is_(None)
            )
        )
        if row is None:
            now = datetime.now(UTC)
            row = Possession(
                id=uuid4(),
                booking_id=booking.id,
                handover_date=None,
                evidence_document_id=None,
                handed_over_by=None,
                status="pending",
                created_at=now,
                updated_at=now,
                created_by=actor_user_id,
                updated_by=actor_user_id,
                version=1,
                archived_at=None,
            )
            s.add(row)
            await s.flush()
        if data.target_status not in POS_TRANSITIONS.get(row.status, frozenset()):
            raise CustomerLifecycleConflictError(
                f"possession cannot move from {row.status} to {data.target_status}"
            )
        if data.target_status == "handed_over" and (
            data.handover_date is None or data.evidence_document_id is None
        ):
            raise CustomerLifecycleConflictError("handover requires date and controlled evidence")
        before = {"status": row.status, "version": row.version}
        row.status = data.target_status
        if data.handover_date:
            row.handover_date = data.handover_date
        if data.evidence_document_id:
            row.evidence_document_id = data.evidence_document_id
        booking_before: dict[str, Any] | None = None
        if data.target_status == "handed_over":
            row.handed_over_by = actor_user_id
            booking_before = {"status": booking.status, "version": booking.version}
            booking.status = "possessed"
            booking.updated_at = datetime.now(UTC)
            booking.updated_by = actor_user_id
            booking.version += 1
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "possession_records",
            row.id,
            "transition",
            before,
            {
                "booking_id": str(row.booking_id),
                "status": row.status,
                "handover_date": row.handover_date,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "handed_over_by": str(row.handed_over_by) if row.handed_over_by else None,
                "version": row.version,
            },
        )
        if booking_before is not None:
            await self._audit(
                s,
                actor_user_id,
                "bookings",
                booking.id,
                "possess",
                booking_before,
                {"status": booking.status, "version": booking.version},
            )
        return possession_summary(row)

    async def link_executed_contract(
        self, s: AsyncSession, *, actor_user_id: UUID, booking_id: UUID, contract_id: UUID
    ) -> BookingContractSummary:
        booking = await self._booking(s, booking_id)
        await self._require(s, actor_user_id, "customer.contract.link", booking.project_id)
        contract = await self._commercial.get_contract(
            s, actor_user_id=actor_user_id, contract_id=contract_id
        )
        if contract.project_id != booking.project_id or contract.party_id != booking.customer_id:
            raise CustomerLifecycleConflictError(
                "contract must belong to booking project and customer"
            )
        if contract.status != "executed" or contract.executed_document_id is None:
            raise CustomerLifecycleConflictError(
                "only an executed contract with evidence may be linked"
            )
        now = datetime.now(UTC)
        row = BookingContract(
            id=uuid4(),
            booking_id=booking.id,
            contract_id=contract.id,
            executed_document_id=contract.executed_document_id,
            linked_at=now,
            linked_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        s.add(row)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise CustomerLifecycleConflictError("booking or contract is already linked") from exc
        await self._audit(
            s,
            actor_user_id,
            "booking_contracts",
            row.id,
            "link",
            None,
            {
                "booking_id": str(row.booking_id),
                "contract_id": str(row.contract_id),
                "executed_document_id": str(row.executed_document_id),
                "linked_by": str(actor_user_id),
                "version": 1,
            },
        )
        return contract_summary(row)
