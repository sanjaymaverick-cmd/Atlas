"""Audited Phase 4 commercial workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.commercial.contracts import (
    CommercialConflictError,
    CommercialNotAuthorisedError,
    CommercialNotFoundError,
)
from atlas.modules.commercial.models import (
    Budget,
    BudgetLine,
    Contract,
    ContractMilestone,
    InsurancePolicy,
    KycRecord,
    LabourComplianceRecord,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorOnboarding,
)
from atlas.modules.commercial.schemas import (
    BudgetCreate,
    BudgetLineCreate,
    BudgetLineSummary,
    BudgetSummary,
    ContractCreate,
    ContractExecution,
    ContractSummary,
    InsuranceCreate,
    InsuranceSummary,
    KycRecordCreate,
    KycRecordSummary,
    LabourComplianceCreate,
    LabourComplianceSummary,
    MilestoneCreate,
    MilestoneSummary,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
    PurchaseOrderLineSummary,
    PurchaseOrderSummary,
    VendorOnboardingSummary,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

BUDGET_TRANSITIONS = {
    "draft": frozenset({"submitted"}),
    "submitted": frozenset({"approved", "draft"}),
    "approved": frozenset({"revised"}),
    "revised": frozenset({"submitted"}),
}
VENDOR_TRANSITIONS = {
    "invited": frozenset({"kyc_submitted", "rejected"}),
    "kyc_submitted": frozenset({"bank_verified", "rejected"}),
    "bank_verified": frozenset({"compliance_docs_submitted", "rejected"}),
    "compliance_docs_submitted": frozenset({"approved", "rejected"}),
    "approved": frozenset({"active"}),
}
PO_TRANSITIONS = {
    "draft": frozenset({"submitted", "cancelled"}),
    "submitted": frozenset({"approved", "draft", "cancelled"}),
    "approved": frozenset({"issued", "cancelled"}),
    "issued": frozenset({"partially_received", "closed", "cancelled"}),
    "partially_received": frozenset({"closed", "cancelled"}),
}
CONTRACT_TRANSITIONS = {
    "draft": frozenset({"submitted", "cancelled"}),
    "submitted": frozenset({"under_review", "rejected", "cancelled"}),
    "under_review": frozenset({"clarification_required", "approved", "rejected"}),
    "clarification_required": frozenset({"resubmitted", "cancelled"}),
    "resubmitted": frozenset({"under_review"}),
    "approved": frozenset({"contract_execution", "expired", "cancelled"}),
    "contract_execution": frozenset({"executed", "cancelled"}),
    "executed": frozenset({"closed", "superseded"}),
}
INSURANCE_TRANSITIONS = {
    "active": frozenset({"expired", "claimed", "cancelled"}),
    "claimed": frozenset({"expired", "cancelled"}),
}
LABOUR_TRANSITIONS = {
    "pending": frozenset({"compliant", "non_compliant"}),
    "non_compliant": frozenset({"pending", "compliant"}),
    "compliant": frozenset({"pending", "non_compliant"}),
}


def budget_summary(row: Budget) -> BudgetSummary:
    return BudgetSummary(
        row.id,
        row.project_id,
        row.legal_entity_id,
        row.total_amount,
        row.status,
        row.approved_at,
        row.version,
        row.archived_at,
    )


def budget_line_summary(row: BudgetLine) -> BudgetLineSummary:
    return BudgetLineSummary(
        row.id,
        row.budget_id,
        row.cost_code_id,
        row.description,
        row.planned_amount,
        row.committed_amount,
        row.actual_amount,
        row.status,
        row.version,
        row.archived_at,
    )


def onboarding_summary(row: VendorOnboarding) -> VendorOnboardingSummary:
    return VendorOnboardingSummary(
        row.id, row.vendor_id, row.status, row.approved_by, row.version, row.archived_at
    )


def kyc_summary(row: KycRecord) -> KycRecordSummary:
    return KycRecordSummary(
        row.id,
        row.party_id,
        row.document_type,
        row.document_reference,
        row.evidence_document_id,
        row.verification_status,
        row.verified_by,
        row.version,
        row.archived_at,
    )


def po_summary(row: PurchaseOrder) -> PurchaseOrderSummary:
    return PurchaseOrderSummary(
        row.id,
        row.project_id,
        row.vendor_id,
        row.budget_line_id,
        row.total_amount,
        row.status,
        row.issued_at,
        row.version,
        row.archived_at,
    )


def po_line_summary(row: PurchaseOrderLine) -> PurchaseOrderLineSummary:
    return PurchaseOrderLineSummary(
        row.id,
        row.purchase_order_id,
        row.cost_code_id,
        row.description,
        row.quantity,
        row.unit_price,
        row.amount,
        row.version,
        row.archived_at,
    )


def contract_summary(row: Contract) -> ContractSummary:
    return ContractSummary(
        row.id,
        row.project_id,
        row.party_id,
        row.contract_type,
        row.value,
        row.status,
        row.execution_method,
        row.executed_at,
        row.executed_document_id,
        row.version,
        row.archived_at,
    )


def milestone_summary(row: ContractMilestone) -> MilestoneSummary:
    return MilestoneSummary(
        row.id,
        row.contract_id,
        row.description,
        row.due_date,
        row.amount,
        row.status,
        row.version,
        row.archived_at,
    )


def insurance_summary(row: InsurancePolicy) -> InsuranceSummary:
    return InsuranceSummary(
        row.id,
        row.project_id,
        row.contract_id,
        row.vendor_id,
        row.policy_number,
        row.insurer,
        row.coverage_type,
        row.sum_insured,
        row.valid_from,
        row.valid_to,
        row.status,
        row.version,
        row.archived_at,
    )


def labour_summary(row: LabourComplianceRecord) -> LabourComplianceSummary:
    return LabourComplianceSummary(
        row.id,
        row.contractor_id,
        row.project_id,
        row.pf_registration_number,
        row.esi_registration_number,
        row.contract_labour_licence_number,
        row.minimum_wage_evidence_ref,
        row.status,
        row.version,
        row.archived_at,
    )


class CommercialService:
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
        if not await self._identity.check_scoped_role(
            session,
            user_id=actor_user_id,
            permission_code=permission,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
        ):
            raise CommercialNotAuthorisedError(f"user may not {permission} in the requested scope")

    async def _audit(
        self,
        session: AsyncSession,
        *,
        actor: UUID,
        schema: str,
        table: str,
        row_id: UUID,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        await record_event(
            session,
            actor_user_id=actor,
            entity_schema=schema,
            entity_table=table,
            entity_id=row_id,
            action=action,
            before_state=before,
            after_state=after,
        )

    async def create_budget(
        self, session: AsyncSession, *, actor_user_id: UUID, data: BudgetCreate
    ) -> BudgetSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="budget.create",
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = Budget(
            id=uuid4(),
            project_id=data.project_id,
            legal_entity_id=data.legal_entity_id,
            total_amount=data.total_amount,
            status="draft",
            approved_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="budget",
            table="budgets",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "legal_entity_id": str(row.legal_entity_id),
                "total_amount": row.total_amount,
                "status": row.status,
                "version": row.version,
            },
        )
        return budget_summary(row)

    async def list_budgets(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[BudgetSummary]:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="budget.read",
            project_id=project_id,
        )
        result = await session.execute(
            select(Budget)
            .where(Budget.project_id == project_id, Budget.archived_at.is_(None))
            .order_by(Budget.created_at)
        )
        return [budget_summary(row) for row in result.scalars()]

    async def add_budget_line(
        self, session: AsyncSession, *, actor_user_id: UUID, budget_id: UUID, data: BudgetLineCreate
    ) -> BudgetLineSummary:
        budget = await session.get(Budget, budget_id)
        if budget is None:
            raise CommercialNotFoundError(f"budget {budget_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="budget.update",
            legal_entity_id=budget.legal_entity_id,
            project_id=budget.project_id,
        )
        if budget.status not in {"draft", "revised"}:
            raise CommercialConflictError("budget lines may only change in draft or revised state")
        now = datetime.now(UTC)
        row = BudgetLine(
            id=uuid4(),
            budget_id=budget_id,
            cost_code_id=data.cost_code_id,
            description=data.description,
            planned_amount=data.planned_amount,
            committed_amount=Decimal(0),
            actual_amount=Decimal(0),
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
        await self._audit(
            session,
            actor=actor_user_id,
            schema="budget",
            table="budget_lines",
            row_id=row.id,
            action="create",
            before=None,
            after={"budget_id": str(budget_id), "planned_amount": row.planned_amount, "version": 1},
        )
        return budget_line_summary(row)

    async def transition_budget(
        self, session: AsyncSession, *, actor_user_id: UUID, budget_id: UUID, target_status: str
    ) -> BudgetSummary:
        row = await session.get(Budget, budget_id)
        if row is None:
            raise CommercialNotFoundError(f"budget {budget_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="budget.approve" if target_status == "approved" else "budget.update",
            legal_entity_id=row.legal_entity_id,
            project_id=row.project_id,
        )
        if target_status not in BUDGET_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"budget cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.approved_at = datetime.now(UTC) if target_status == "approved" else None
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="budget",
            table="budgets",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return budget_summary(row)

    async def invite_vendor(
        self, session: AsyncSession, *, actor_user_id: UUID, vendor_id: UUID
    ) -> VendorOnboardingSummary:
        await self._require(session, actor_user_id=actor_user_id, permission="vendor.onboard")
        now = datetime.now(UTC)
        row = VendorOnboarding(
            id=uuid4(),
            vendor_id=vendor_id,
            status="invited",
            invited_at=now,
            kyc_completed_at=None,
            bank_verified_at=None,
            compliance_docs_completed_at=None,
            approved_at=None,
            approved_by=None,
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
            raise CommercialConflictError("vendor already has an onboarding record") from exc
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="vendor_onboardings",
            row_id=row.id,
            action="create",
            before=None,
            after={"vendor_id": str(vendor_id), "status": "invited", "version": 1},
        )
        return onboarding_summary(row)

    async def transition_vendor(
        self, session: AsyncSession, *, actor_user_id: UUID, onboarding_id: UUID, target_status: str
    ) -> VendorOnboardingSummary:
        row = await session.get(VendorOnboarding, onboarding_id)
        if row is None:
            raise CommercialNotFoundError(f"onboarding {onboarding_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="vendor.approve"
            if target_status in {"approved", "active"}
            else "vendor.onboard",
        )
        if target_status not in VENDOR_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"vendor onboarding cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        now = datetime.now(UTC)
        row.status = target_status
        row.updated_at = now
        row.updated_by = actor_user_id
        row.version += 1
        if target_status == "kyc_submitted":
            row.kyc_completed_at = now
        elif target_status == "bank_verified":
            row.bank_verified_at = now
        elif target_status == "compliance_docs_submitted":
            row.compliance_docs_completed_at = now
        elif target_status == "approved":
            row.approved_at = now
            row.approved_by = actor_user_id
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="vendor_onboardings",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return onboarding_summary(row)

    async def add_kyc_record(
        self, session: AsyncSession, *, actor_user_id: UUID, data: KycRecordCreate
    ) -> KycRecordSummary:
        await self._require(session, actor_user_id=actor_user_id, permission="vendor.onboard")
        now = datetime.now(UTC)
        row = KycRecord(
            id=uuid4(),
            party_id=data.party_id,
            document_type=data.document_type,
            document_reference=data.document_reference,
            object_storage_key=None,
            evidence_document_id=data.evidence_document_id,
            verification_status="pending",
            verified_by=None,
            verified_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="kyc_records",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "party_id": str(row.party_id),
                "document_type": row.document_type,
                "evidence_document_id": str(row.evidence_document_id),
                "verification_status": "pending",
                "version": 1,
            },
        )
        return kyc_summary(row)

    async def verify_kyc_record(
        self, session: AsyncSession, *, actor_user_id: UUID, record_id: UUID, approve: bool
    ) -> KycRecordSummary:
        row = await session.get(KycRecord, record_id)
        if row is None:
            raise CommercialNotFoundError(f"KYC record {record_id} does not exist")
        await self._require(session, actor_user_id=actor_user_id, permission="vendor.verify")
        if row.verification_status != "pending":
            raise CommercialConflictError("KYC decision is final")
        before = {"verification_status": row.verification_status, "version": row.version}
        row.verification_status = "verified" if approve else "rejected"
        row.verified_by = actor_user_id
        row.verified_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="kyc_records",
            row_id=row.id,
            action="verify",
            before=before,
            after={
                "verification_status": row.verification_status,
                "verified_by": str(actor_user_id),
                "version": row.version,
            },
        )
        return kyc_summary(row)

    async def create_purchase_order(
        self, session: AsyncSession, *, actor_user_id: UUID, data: PurchaseOrderCreate
    ) -> PurchaseOrderSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="procurement.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = PurchaseOrder(
            id=uuid4(),
            project_id=data.project_id,
            vendor_id=data.vendor_id,
            budget_line_id=data.budget_line_id,
            total_amount=data.total_amount,
            status="draft",
            issued_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="procurement",
            table="purchase_orders",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "vendor_id": str(row.vendor_id),
                "budget_line_id": str(row.budget_line_id) if row.budget_line_id else None,
                "total_amount": row.total_amount,
                "status": "draft",
                "version": 1,
            },
        )
        return po_summary(row)

    async def add_purchase_order_line(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        purchase_order_id: UUID,
        data: PurchaseOrderLineCreate,
    ) -> PurchaseOrderLineSummary:
        order = await session.get(PurchaseOrder, purchase_order_id)
        if order is None:
            raise CommercialNotFoundError(f"purchase order {purchase_order_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="procurement.update",
            project_id=order.project_id,
        )
        if order.status != "draft":
            raise CommercialConflictError("purchase-order lines may only change in draft")
        now = datetime.now(UTC)
        row = PurchaseOrderLine(
            id=uuid4(),
            purchase_order_id=purchase_order_id,
            cost_code_id=data.cost_code_id,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            amount=data.amount,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="procurement",
            table="purchase_order_lines",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "purchase_order_id": str(purchase_order_id),
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "amount": row.amount,
                "version": 1,
            },
        )
        return po_line_summary(row)

    async def transition_purchase_order(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        purchase_order_id: UUID,
        target_status: str,
    ) -> PurchaseOrderSummary:
        row = await session.get(PurchaseOrder, purchase_order_id)
        if row is None:
            raise CommercialNotFoundError(f"purchase order {purchase_order_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="procurement.approve"
            if target_status in {"approved", "issued"}
            else "procurement.update",
            project_id=row.project_id,
        )
        if target_status not in PO_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"purchase order cannot move from {row.status} to {target_status}"
            )
        if target_status == "issued":
            active = await session.scalar(
                select(VendorOnboarding).where(
                    VendorOnboarding.vendor_id == row.vendor_id,
                    VendorOnboarding.status == "active",
                    VendorOnboarding.archived_at.is_(None),
                )
            )
            if active is None:
                raise CommercialConflictError(
                    "purchase order cannot be issued until vendor onboarding is active"
                )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.issued_at = datetime.now(UTC) if target_status == "issued" else row.issued_at
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="procurement",
            table="purchase_orders",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "issued_at": row.issued_at, "version": row.version},
        )
        return po_summary(row)

    async def create_contract(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ContractCreate
    ) -> ContractSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="contract.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = Contract(
            id=uuid4(),
            project_id=data.project_id,
            party_id=data.party_id,
            contract_type=data.contract_type,
            value=data.value,
            status="draft",
            execution_method=None,
            executed_at=None,
            executed_document_id=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="contracts",
            table="contracts",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "party_id": str(row.party_id),
                "contract_type": row.contract_type,
                "value": row.value,
                "status": "draft",
                "version": 1,
            },
        )
        return contract_summary(row)

    async def add_milestone(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        contract_id: UUID,
        data: MilestoneCreate,
    ) -> MilestoneSummary:
        contract = await session.get(Contract, contract_id)
        if contract is None:
            raise CommercialNotFoundError(f"contract {contract_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="contract.update",
            project_id=contract.project_id,
        )
        if contract.status not in {"draft", "clarification_required"}:
            raise CommercialConflictError("milestones may only change before approval")
        now = datetime.now(UTC)
        row = ContractMilestone(
            id=uuid4(),
            contract_id=contract_id,
            description=data.description,
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
        session.add(row)
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="contracts",
            table="contract_milestones",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "contract_id": str(contract_id),
                "due_date": row.due_date,
                "amount": row.amount,
                "status": "pending",
                "version": 1,
            },
        )
        return milestone_summary(row)

    async def transition_contract(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        contract_id: UUID,
        target_status: str,
        execution: ContractExecution | None = None,
    ) -> ContractSummary:
        row = await session.get(Contract, contract_id)
        if row is None:
            raise CommercialNotFoundError(f"contract {contract_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="contract.approve"
            if target_status in {"approved", "contract_execution", "executed"}
            else "contract.update",
            project_id=row.project_id,
        )
        if target_status not in CONTRACT_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"contract cannot move from {row.status} to {target_status}"
            )
        if target_status == "executed" and execution is None:
            raise CommercialConflictError(
                "executed contract requires method and immutable document evidence"
            )
        if target_status != "executed" and execution is not None:
            raise CommercialConflictError(
                "execution evidence is accepted only for executed transition"
            )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        if execution is not None:
            row.execution_method = execution.execution_method
            row.executed_document_id = execution.executed_document_id
            row.executed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="contracts",
            table="contracts",
            row_id=row.id,
            action="transition",
            before=before,
            after={
                "status": row.status,
                "execution_method": row.execution_method,
                "executed_document_id": str(row.executed_document_id)
                if row.executed_document_id
                else None,
                "executed_at": row.executed_at,
                "version": row.version,
            },
        )
        return contract_summary(row)

    async def create_insurance(
        self, session: AsyncSession, *, actor_user_id: UUID, data: InsuranceCreate
    ) -> InsuranceSummary:
        if data.project_id is None and data.contract_id is None and data.vendor_id is None:
            raise CommercialConflictError("insurance requires project, contract, or vendor scope")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="vendor.insurance.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = InsurancePolicy(
            id=uuid4(),
            project_id=data.project_id,
            contract_id=data.contract_id,
            vendor_id=data.vendor_id,
            policy_number=data.policy_number,
            insurer=data.insurer,
            coverage_type=data.coverage_type,
            sum_insured=data.sum_insured,
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
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="insurance_policies",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id) if row.project_id else None,
                "contract_id": str(row.contract_id) if row.contract_id else None,
                "vendor_id": str(row.vendor_id) if row.vendor_id else None,
                "coverage_type": row.coverage_type,
                "status": row.status,
                "version": row.version,
            },
        )
        return insurance_summary(row)

    async def transition_insurance(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        policy_id: UUID,
        target_status: str,
    ) -> InsuranceSummary:
        row = await session.get(InsurancePolicy, policy_id)
        if row is None:
            raise CommercialNotFoundError(f"insurance policy {policy_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="vendor.insurance.update",
            project_id=row.project_id,
        )
        if target_status not in INSURANCE_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"insurance cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="insurance_policies",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return insurance_summary(row)

    async def create_labour_compliance(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        data: LabourComplianceCreate,
    ) -> LabourComplianceSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="vendor.labour.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = LabourComplianceRecord(
            id=uuid4(),
            contractor_id=data.contractor_id,
            project_id=data.project_id,
            pf_registration_number=data.pf_registration_number,
            esi_registration_number=data.esi_registration_number,
            contract_labour_licence_number=data.contract_labour_licence_number,
            minimum_wage_evidence_ref=data.minimum_wage_evidence_ref,
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
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="labour_compliance_records",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "contractor_id": str(row.contractor_id),
                "project_id": str(row.project_id) if row.project_id else None,
                "status": row.status,
                "version": row.version,
            },
        )
        return labour_summary(row)

    async def transition_labour_compliance(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        record_id: UUID,
        target_status: str,
    ) -> LabourComplianceSummary:
        row = await session.get(LabourComplianceRecord, record_id)
        if row is None:
            raise CommercialNotFoundError(f"labour record {record_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission="vendor.labour.verify",
            project_id=row.project_id,
        )
        if target_status not in LABOUR_TRANSITIONS.get(row.status, frozenset()):
            raise CommercialConflictError(
                f"labour record cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="vendor_onboarding",
            table="labour_compliance_records",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return labour_summary(row)
