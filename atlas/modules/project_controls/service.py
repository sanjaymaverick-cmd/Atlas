"""Audited Phase 6 project-control workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.project_controls.contracts import (
    ProjectControlsConflictError,
    ProjectControlsNotAuthorisedError,
    ProjectControlsNotFoundError,
)
from atlas.modules.project_controls.models import (
    BimImport,
    BimObject,
    CostCode,
    Material,
    MaterialIssuance,
    MaterialReceipt,
    QuantityItem,
)
from atlas.modules.project_controls.schemas import (
    BimImportCreate,
    BimImportSummary,
    CostCodeCreate,
    CostCodeSummary,
    IssuanceCreate,
    IssuanceSummary,
    MaterialCreate,
    MaterialSummary,
    QuantityCreate,
    QuantitySummary,
    ReceiptCreate,
    ReceiptSummary,
)
from atlas.platform.audit.writer import record_event

BIM_TRANSITIONS = {
    "received": frozenset({"validating"}),
    "validating": frozenset({"validated", "rejected"}),
    "validated": frozenset({"imported"}),
}


def bim_summary(r: BimImport) -> BimImportSummary:
    if r.source_document_id is None:
        raise ProjectControlsConflictError("legacy BIM import has no classified source document")
    return BimImportSummary(
        r.id,
        r.project_id,
        r.source_document_id,
        r.import_status,
        r.validated_at,
        r.validated_by,
        r.version,
    )


def code_summary(r: CostCode) -> CostCodeSummary:
    return CostCodeSummary(
        r.id, r.project_id, r.code, r.description, r.wbs_level, r.parent_cost_code_id, r.version
    )


def quantity_summary(r: QuantityItem) -> QuantitySummary:
    return QuantitySummary(
        r.id,
        r.project_id,
        r.calculated_quantity,
        r.verified_quantity,
        r.final_approved_quantity,
        r.tolerance_pct,
        r.status,
        r.version,
    )


def material_summary(r: Material) -> MaterialSummary:
    return MaterialSummary(r.id, r.name, r.unit_of_measure, r.category, r.version)


def receipt_summary(r: MaterialReceipt) -> ReceiptSummary:
    return ReceiptSummary(
        r.id,
        r.project_id,
        r.material_id,
        r.quantity_received,
        r.received_date,
        r.status,
        r.certificate_document_id,
        r.version,
    )


def issuance_summary(r: MaterialIssuance) -> IssuanceSummary:
    return IssuanceSummary(
        r.id,
        r.project_id,
        r.material_id,
        r.material_receipt_id,
        r.quantity_issued,
        r.issued_date,
        r.evidence_document_id,
        r.version,
    )


PERM_READ = "project_controls.read"


class ProjectControlsService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(
        self, s: AsyncSession, actor: UUID, permission: str, project: UUID | None
    ) -> None:
        if not await self._identity.check_scoped_role(
            s, user_id=actor, permission_code=permission, project_id=project
        ):
            raise ProjectControlsNotAuthorisedError(
                f"user may not {permission} in the requested scope"
            )

    async def _audit(
        self,
        s: AsyncSession,
        actor: UUID,
        schema: str,
        table: str,
        row: UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
    ) -> None:
        await record_event(
            s,
            actor_user_id=actor,
            entity_schema=schema,
            entity_table=table,
            entity_id=row,
            action=action,
            before_state=before,
            after_state=after,
        )

    async def register_bim_import(
        self, s: AsyncSession, *, actor_user_id: UUID, data: BimImportCreate
    ) -> BimImportSummary:
        await self._require(s, actor_user_id, "design.bim.create", data.project_id)
        now = datetime.now(UTC)
        row = BimImport(
            id=uuid4(),
            project_id=data.project_id,
            source_file_reference=str(data.source_document_id),
            source_document_id=data.source_document_id,
            import_status="received",
            validated_at=None,
            validated_by=None,
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
            "design",
            "bim_imports",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "source_document_id": str(data.source_document_id),
                "status": "received",
                "version": 1,
            },
        )
        return bim_summary(row)

    async def transition_bim_import(
        self, s: AsyncSession, *, actor_user_id: UUID, import_id: UUID, target_status: str
    ) -> BimImportSummary:
        row = await s.get(BimImport, import_id)
        if row is None:
            raise ProjectControlsNotFoundError(f"BIM import {import_id} does not exist")
        if row.source_document_id is None:
            raise ProjectControlsConflictError(
                "legacy BIM import must be migrated to a classified document before transition"
            )
        await self._require(s, actor_user_id, "design.bim.validate", row.project_id)
        if target_status not in BIM_TRANSITIONS.get(row.import_status, frozenset()):
            raise ProjectControlsConflictError(
                f"BIM import cannot move from {row.import_status} to {target_status}"
            )
        before = {"status": row.import_status, "version": row.version}
        row.import_status = target_status
        if target_status == "validated":
            row.validated_at = datetime.now(UTC)
            row.validated_by = actor_user_id
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "design",
            "bim_imports",
            row.id,
            "transition",
            before,
            {
                "status": row.import_status,
                "validated_by": str(row.validated_by) if row.validated_by else None,
                "version": row.version,
            },
        )
        return bim_summary(row)

    async def create_cost_code(
        self, s: AsyncSession, *, actor_user_id: UUID, data: CostCodeCreate
    ) -> CostCodeSummary:
        await self._require(s, actor_user_id, "quantities.cost_code.create", data.project_id)
        level = 1
        if data.parent_cost_code_id:
            parent = await s.get(CostCode, data.parent_cost_code_id)
            if parent is None or parent.project_id != data.project_id:
                raise ProjectControlsConflictError(
                    "parent cost code must exist in the same project"
                )
            level = parent.wbs_level + 1
        now = datetime.now(UTC)
        row = CostCode(
            id=uuid4(),
            project_id=data.project_id,
            code=data.code,
            description=data.description,
            wbs_level=level,
            parent_cost_code_id=data.parent_cost_code_id,
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
            raise ProjectControlsConflictError("cost code already exists in this project") from exc
        await self._audit(
            s,
            actor_user_id,
            "quantities",
            "cost_codes",
            row.id,
            "create",
            None,
            {"project_id": str(row.project_id), "code": row.code, "wbs_level": level, "version": 1},
        )
        return code_summary(row)

    async def create_quantity(
        self, s: AsyncSession, *, actor_user_id: UUID, data: QuantityCreate
    ) -> QuantitySummary:
        await self._require(s, actor_user_id, "quantities.item.create", data.project_id)
        if data.calculated_quantity < 0 or not Decimal(0) <= data.tolerance_pct <= Decimal(100):
            raise ProjectControlsConflictError("quantity and tolerance are outside allowed bounds")
        if data.cost_code_id is not None:
            cost_code = await s.get(CostCode, data.cost_code_id)
            if cost_code is None or cost_code.project_id != data.project_id:
                raise ProjectControlsConflictError("cost code must exist in the same project")
        if data.bim_object_id is not None:
            bim_object = await s.get(BimObject, data.bim_object_id)
            if bim_object is None or bim_object.project_id != data.project_id:
                raise ProjectControlsConflictError("BIM object must exist in the same project")
        now = datetime.now(UTC)
        row = QuantityItem(
            id=uuid4(),
            project_id=data.project_id,
            cost_code_id=data.cost_code_id,
            bim_object_id=data.bim_object_id,
            work_package=data.work_package,
            calculated_quantity=data.calculated_quantity,
            verified_quantity=None,
            proposed_resolution=None,
            final_approved_quantity=None,
            tolerance_pct=data.tolerance_pct,
            status="calculated",
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
            "quantities",
            "quantity_items",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "calculated_quantity": str(row.calculated_quantity),
                "tolerance_pct": str(row.tolerance_pct),
                "status": row.status,
                "version": 1,
            },
        )
        return quantity_summary(row)

    async def verify_quantity(
        self, s: AsyncSession, *, actor_user_id: UUID, quantity_id: UUID, verified_quantity: Decimal
    ) -> QuantitySummary:
        row = await s.get(QuantityItem, quantity_id)
        if row is None:
            raise ProjectControlsNotFoundError(f"quantity {quantity_id} does not exist")
        await self._require(s, actor_user_id, "quantities.item.verify", row.project_id)
        if row.status not in {"calculated", "submitted"} or verified_quantity < 0:
            raise ProjectControlsConflictError("quantity cannot be verified in its current state")
        calculated = row.calculated_quantity or Decimal(0)
        difference = abs(verified_quantity - calculated)
        pct = (
            Decimal(0)
            if calculated == 0 and difference == 0
            else (Decimal(100) if calculated == 0 else difference / calculated * 100)
        )
        before = {"status": row.status, "version": row.version}
        row.verified_quantity = verified_quantity
        row.status = "within_tolerance" if pct <= row.tolerance_pct else "discrepancy"
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quantities",
            "quantity_items",
            row.id,
            "verify",
            before,
            {
                "verified_quantity": str(verified_quantity),
                "variance_pct": str(pct),
                "status": row.status,
                "version": row.version,
            },
        )
        return quantity_summary(row)

    async def approve_quantity(
        self, s: AsyncSession, *, actor_user_id: UUID, quantity_id: UUID, final_quantity: Decimal
    ) -> QuantitySummary:
        row = await s.get(QuantityItem, quantity_id)
        if row is None:
            raise ProjectControlsNotFoundError(f"quantity {quantity_id} does not exist")
        await self._require(s, actor_user_id, "quantities.item.approve", row.project_id)
        if row.status not in {"within_tolerance", "under_review"} or final_quantity < 0:
            raise ProjectControlsConflictError("quantity cannot be approved in its current state")
        before = {"status": row.status, "version": row.version}
        row.final_approved_quantity = final_quantity
        row.status = "approved"
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quantities",
            "quantity_items",
            row.id,
            "approve",
            before,
            {
                "final_approved_quantity": str(final_quantity),
                "status": "approved",
                "version": row.version,
            },
        )
        return quantity_summary(row)

    async def create_material(
        self, s: AsyncSession, *, actor_user_id: UUID, data: MaterialCreate
    ) -> MaterialSummary:
        await self._require(s, actor_user_id, "inventory.material.create", None)
        now = datetime.now(UTC)
        row = Material(
            id=uuid4(),
            name=data.name,
            unit_of_measure=data.unit_of_measure,
            category=data.category,
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
            raise ProjectControlsConflictError("material name and unit already exist") from exc
        await self._audit(
            s,
            actor_user_id,
            "inventory",
            "materials",
            row.id,
            "create",
            None,
            {
                "name": row.name,
                "unit_of_measure": row.unit_of_measure,
                "category": row.category,
                "version": 1,
            },
        )
        return material_summary(row)

    async def record_receipt(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ReceiptCreate
    ) -> ReceiptSummary:
        await self._require(s, actor_user_id, "inventory.receipt.create", data.project_id)
        if data.quantity_received <= 0 or data.status not in {"received", "partial", "rejected"}:
            raise ProjectControlsConflictError("receipt quantity or status is invalid")
        if data.status == "rejected":
            raise ProjectControlsConflictError(
                "rejected deliveries require a zero-stock rejection workflow"
            )
        now = datetime.now(UTC)
        row = MaterialReceipt(
            id=uuid4(),
            project_id=data.project_id,
            purchase_order_id=data.purchase_order_id,
            material_id=data.material_id,
            quantity_received=data.quantity_received,
            batch_reference=data.batch_reference,
            certificate_document_id=data.certificate_document_id,
            received_date=data.received_date,
            status=data.status,
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
            "inventory",
            "material_receipts",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "material_id": str(row.material_id),
                "quantity_received": str(row.quantity_received),
                "certificate_document_id": str(row.certificate_document_id)
                if row.certificate_document_id
                else None,
                "status": row.status,
                "version": 1,
            },
        )
        return receipt_summary(row)

    async def issue_material(
        self, s: AsyncSession, *, actor_user_id: UUID, receipt_id: UUID, data: IssuanceCreate
    ) -> IssuanceSummary:
        receipt = await s.scalar(
            select(MaterialReceipt).where(MaterialReceipt.id == receipt_id).with_for_update()
        )
        if receipt is None:
            raise ProjectControlsNotFoundError(f"material receipt {receipt_id} does not exist")
        await self._require(s, actor_user_id, "inventory.issuance.create", receipt.project_id)
        if data.quantity_issued <= 0 or receipt.status not in {"received", "partial"}:
            raise ProjectControlsConflictError("material cannot be issued from this receipt")
        issued = await s.scalar(
            select(func.coalesce(func.sum(MaterialIssuance.quantity_issued), 0)).where(
                MaterialIssuance.material_receipt_id == receipt_id,
                MaterialIssuance.archived_at.is_(None),
            )
        )
        if Decimal(issued or 0) + data.quantity_issued > receipt.quantity_received:
            raise ProjectControlsConflictError("issuance exceeds unissued receipt quantity")
        now = datetime.now(UTC)
        row = MaterialIssuance(
            id=uuid4(),
            project_id=receipt.project_id,
            material_id=receipt.material_id,
            material_receipt_id=receipt.id,
            quantity_issued=data.quantity_issued,
            issued_to=data.issued_to,
            issued_date=data.issued_date,
            evidence_document_id=data.evidence_document_id,
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
            "inventory",
            "material_issuances",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "material_id": str(row.material_id),
                "material_receipt_id": str(row.material_receipt_id),
                "quantity_issued": str(row.quantity_issued),
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "version": 1,
            },
        )
        return issuance_summary(row)

    # -- reads ------------------------------------------------------------
    # Added 2026-08-20; this module previously published writes only.

    async def list_bim_imports(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[BimImportSummary]:
        await self._require(s, actor_user_id, PERM_READ, project_id)
        result = await s.execute(
            select(BimImport)
            .where(BimImport.project_id == project_id)
            .where(BimImport.archived_at.is_(None))
            .order_by(BimImport.created_at)
        )
        return [bim_summary(row) for row in result.scalars()]

    async def list_cost_codes(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[CostCodeSummary]:
        await self._require(s, actor_user_id, PERM_READ, project_id)
        result = await s.execute(
            select(CostCode)
            .where(CostCode.project_id == project_id)
            .where(CostCode.archived_at.is_(None))
            .order_by(CostCode.code)
        )
        return [code_summary(row) for row in result.scalars()]

    async def list_quantities(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[QuantitySummary]:
        await self._require(s, actor_user_id, PERM_READ, project_id)
        result = await s.execute(
            select(QuantityItem)
            .where(QuantityItem.project_id == project_id)
            .where(QuantityItem.archived_at.is_(None))
            .order_by(QuantityItem.created_at)
        )
        return [quantity_summary(row) for row in result.scalars()]

    async def list_receipts(
        self, s: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> list[ReceiptSummary]:
        await self._require(s, actor_user_id, PERM_READ, project_id)
        result = await s.execute(
            select(MaterialReceipt)
            .where(MaterialReceipt.project_id == project_id)
            .where(MaterialReceipt.archived_at.is_(None))
            .order_by(MaterialReceipt.received_date)
        )
        return [receipt_summary(row) for row in result.scalars()]

    async def list_materials(
        self, s: AsyncSession, *, actor_user_id: UUID
    ) -> list[MaterialSummary]:
        # The material master is estate-wide, not project-scoped, so this needs
        # a global grant — the same scope create_material requires.
        await self._require(s, actor_user_id, PERM_READ, None)
        result = await s.execute(
            select(Material).where(Material.archived_at.is_(None)).order_by(Material.name)
        )
        return [material_summary(row) for row in result.scalars()]
