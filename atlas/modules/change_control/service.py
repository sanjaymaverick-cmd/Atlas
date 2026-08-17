"""Audited Phase 7 workflow state machines."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.change_control.contracts import (
    ChangeControlConflictError,
    ChangeControlNotAuthorisedError,
    ChangeControlNotFoundError,
)
from atlas.modules.change_control.models import ChangeRequest, DiscrepancyCase, Ncr, Rfi
from atlas.modules.change_control.schemas import (
    ChangeCreate,
    ChangeSummary,
    DiscrepancyCreate,
    DiscrepancySummary,
    DiscrepancyTransition,
    NcrCreate,
    NcrSummary,
    NcrTransition,
    RfiCreate,
    RfiResponse,
    RfiSummary,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

CHANGE_PATH = (
    "requested",
    "feasibility_review",
    "structural_review",
    "revised_drawings",
    "quantity_impact",
    "budget_impact",
    "procurement_impact",
    "contract_impact",
    "commercial_quotation",
    "approved",
    "implemented",
    "verified",
    "closed",
)
CHANGE_TRANSITIONS = {
    value: frozenset({CHANGE_PATH[i + 1], "rejected"}) for i, value in enumerate(CHANGE_PATH[:-1])
}
CHANGE_TRANSITIONS["approved"] = frozenset({"implemented"})
CHANGE_TRANSITIONS["implemented"] = frozenset({"verified"})
CHANGE_TRANSITIONS["verified"] = frozenset({"closed"})
RFI_TRANSITIONS = {
    "raised": frozenset({"routed", "overdue"}),
    "routed": frozenset({"responded", "overdue"}),
    "overdue": frozenset({"routed", "responded"}),
    "responded": frozenset({"closed"}),
}
NCR_TRANSITIONS = {
    "raised": frozenset({"corrective_action_assigned"}),
    "corrective_action_assigned": frozenset({"reinspection_scheduled"}),
    "reinspection_scheduled": frozenset({"closed"}),
}
DISCREPANCY_TRANSITIONS = {
    "open": frozenset({"explanation_provided"}),
    "explanation_provided": frozenset({"engineering_review"}),
    "engineering_review": frozenset({"owner_approval_required", "resolved"}),
    "owner_approval_required": frozenset({"resolved"}),
}


def change_summary(r: ChangeRequest) -> ChangeSummary:
    return ChangeSummary(
        r.id, r.project_id, r.status, r.evidence_document_id, r.decided_by, r.decided_at, r.version
    )


def rfi_summary(r: Rfi) -> RfiSummary:
    return RfiSummary(
        r.id,
        r.project_id,
        r.routed_to,
        r.sla_due_at,
        r.status,
        r.responded_by,
        r.responded_at,
        r.version,
    )


def ncr_summary(r: Ncr) -> NcrSummary:
    return NcrSummary(
        r.id,
        r.project_id,
        r.severity,
        r.status,
        r.evidence_document_id,
        r.reinspection_id,
        r.closed_by,
        r.closed_at,
        r.version,
    )


def discrepancy_summary(r: DiscrepancyCase) -> DiscrepancySummary:
    return DiscrepancySummary(
        r.id,
        r.project_id,
        r.quantity_item_id,
        r.status,
        r.evidence_document_id,
        r.resolved_by,
        r.resolved_at,
        r.version,
    )


class ChangeControlService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(self, s: AsyncSession, actor: UUID, permission: str, project: UUID) -> None:
        if not await self._identity.check_scoped_role(
            s, user_id=actor, permission_code=permission, project_id=project
        ):
            raise ChangeControlNotAuthorisedError(f"user may not {permission} in requested scope")

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

    async def create_change(
        self, s: AsyncSession, *, actor_user_id: UUID, data: ChangeCreate
    ) -> ChangeSummary:
        await self._require(s, actor_user_id, "change.create", data.project_id)
        if data.budget_impact is not None and data.budget_impact < 0:
            raise ChangeControlConflictError("budget impact may not be negative")
        now = datetime.now(UTC)
        row = ChangeRequest(
            id=uuid4(),
            project_id=data.project_id,
            description=data.description,
            schedule_impact=data.schedule_impact,
            budget_impact=data.budget_impact,
            evidence_document_id=data.evidence_document_id,
            requested_by=actor_user_id,
            decided_by=None,
            decided_at=None,
            status="requested",
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
            "construction",
            "change_requests",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "has_schedule_impact": row.schedule_impact is not None,
                "budget_impact_recorded": row.budget_impact is not None,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "status": row.status,
                "version": 1,
            },
        )
        return change_summary(row)

    async def transition_change(
        self, s: AsyncSession, *, actor_user_id: UUID, change_id: UUID, target_status: str
    ) -> ChangeSummary:
        row = await s.get(ChangeRequest, change_id)
        if row is None:
            raise ChangeControlNotFoundError(f"change {change_id} does not exist")
        permission = (
            "change.decide" if target_status in {"approved", "rejected"} else "change.transition"
        )
        await self._require(s, actor_user_id, permission, row.project_id)
        if target_status not in CHANGE_TRANSITIONS.get(row.status, frozenset()):
            raise ChangeControlConflictError(
                f"change cannot move from {row.status} to {target_status}"
            )
        if target_status == "approved" and row.evidence_document_id is None:
            raise ChangeControlConflictError("approved change requires controlled evidence")
        if target_status == "approved" and row.requested_by == actor_user_id:
            raise ChangeControlNotAuthorisedError(
                "change requester may not approve their own change"
            )
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        if target_status in {"approved", "rejected"}:
            row.decided_by = actor_user_id
            row.decided_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "construction",
            "change_requests",
            row.id,
            "transition",
            before,
            {
                "status": row.status,
                "decided_by": str(row.decided_by) if row.decided_by else None,
                "version": row.version,
            },
        )
        return change_summary(row)

    async def create_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, data: RfiCreate
    ) -> RfiSummary:
        await self._require(s, actor_user_id, "quality.rfi.create", data.project_id)
        now = datetime.now(UTC)
        status = "routed" if data.routed_to else "raised"
        row = Rfi(
            id=uuid4(),
            project_id=data.project_id,
            raised_by=actor_user_id,
            routed_to=data.routed_to,
            question=data.question,
            response=None,
            evidence_document_id=data.evidence_document_id,
            responded_by=None,
            responded_at=None,
            sla_due_at=data.sla_due_at,
            status=status,
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
            "quality",
            "rfis",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "routed_to": str(row.routed_to) if row.routed_to else None,
                "sla_due_at": row.sla_due_at,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "status": row.status,
                "version": 1,
            },
        )
        return rfi_summary(row)

    async def respond_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, rfi_id: UUID, data: RfiResponse
    ) -> RfiSummary:
        row = await s.get(Rfi, rfi_id)
        if row is None:
            raise ChangeControlNotFoundError(f"RFI {rfi_id} does not exist")
        await self._require(s, actor_user_id, "quality.rfi.respond", row.project_id)
        if row.status not in {"routed", "overdue"}:
            raise ChangeControlConflictError("RFI cannot be responded to in its current state")
        if row.routed_to is not None and row.routed_to != actor_user_id:
            raise ChangeControlNotAuthorisedError("only routed recipient may respond")
        before = {"status": row.status, "version": row.version}
        row.response = data.response
        row.evidence_document_id = data.evidence_document_id or row.evidence_document_id
        row.responded_by = actor_user_id
        row.responded_at = datetime.now(UTC)
        row.status = "responded"
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quality",
            "rfis",
            row.id,
            "respond",
            before,
            {
                "status": "responded",
                "responded_by": str(actor_user_id),
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "version": row.version,
            },
        )
        return rfi_summary(row)

    async def transition_rfi(
        self, s: AsyncSession, *, actor_user_id: UUID, rfi_id: UUID, target_status: str
    ) -> RfiSummary:
        row = await s.get(Rfi, rfi_id)
        if row is None:
            raise ChangeControlNotFoundError(f"RFI {rfi_id} does not exist")
        await self._require(
            s,
            actor_user_id,
            "quality.rfi.close" if target_status == "closed" else "quality.rfi.transition",
            row.project_id,
        )
        if target_status not in RFI_TRANSITIONS.get(row.status, frozenset()):
            raise ChangeControlConflictError(
                f"RFI cannot move from {row.status} to {target_status}"
            )
        if target_status == "routed" and row.routed_to is None:
            raise ChangeControlConflictError("RFI requires a routed recipient")
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quality",
            "rfis",
            row.id,
            "transition",
            before,
            {"status": row.status, "version": row.version},
        )
        return rfi_summary(row)

    async def create_ncr(
        self, s: AsyncSession, *, actor_user_id: UUID, data: NcrCreate
    ) -> NcrSummary:
        await self._require(s, actor_user_id, "quality.ncr.create", data.project_id)
        if data.severity not in {"minor", "major", "critical"}:
            raise ChangeControlConflictError("NCR severity is invalid")
        now = datetime.now(UTC)
        row = Ncr(
            id=uuid4(),
            project_id=data.project_id,
            inspection_id=data.inspection_id,
            schedule_activity_id=data.schedule_activity_id,
            severity=data.severity,
            description=data.description,
            corrective_action=None,
            evidence_document_id=data.evidence_document_id,
            reinspection_id=None,
            closed_by=None,
            closed_at=None,
            status="raised",
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
            "quality",
            "ncrs",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "severity": row.severity,
                "inspection_id": str(row.inspection_id) if row.inspection_id else None,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "status": "raised",
                "version": 1,
            },
        )
        return ncr_summary(row)

    async def transition_ncr(
        self, s: AsyncSession, *, actor_user_id: UUID, ncr_id: UUID, data: NcrTransition
    ) -> NcrSummary:
        row = await s.get(Ncr, ncr_id)
        if row is None:
            raise ChangeControlNotFoundError(f"NCR {ncr_id} does not exist")
        await self._require(
            s,
            actor_user_id,
            "quality.ncr.close" if data.target_status == "closed" else "quality.ncr.transition",
            row.project_id,
        )
        if data.target_status not in NCR_TRANSITIONS.get(row.status, frozenset()):
            raise ChangeControlConflictError(
                f"NCR cannot move from {row.status} to {data.target_status}"
            )
        if data.target_status == "corrective_action_assigned" and not data.corrective_action:
            raise ChangeControlConflictError("corrective action is required")
        if data.target_status == "reinspection_scheduled" and data.reinspection_id is None:
            raise ChangeControlConflictError("reinspection is required")
        if data.target_status == "closed" and row.reinspection_id is None:
            raise ChangeControlConflictError("NCR cannot close without reinspection")
        before = {"status": row.status, "version": row.version}
        row.status = data.target_status
        if data.corrective_action:
            row.corrective_action = data.corrective_action
        if data.reinspection_id:
            row.reinspection_id = data.reinspection_id
        if data.evidence_document_id:
            row.evidence_document_id = data.evidence_document_id
        if data.target_status == "closed":
            row.closed_by = actor_user_id
            row.closed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quality",
            "ncrs",
            row.id,
            "transition",
            before,
            {
                "severity": row.severity,
                "status": row.status,
                "corrective_action_recorded": row.corrective_action is not None,
                "reinspection_id": str(row.reinspection_id) if row.reinspection_id else None,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "closed_by": str(row.closed_by) if row.closed_by else None,
                "version": row.version,
            },
        )
        return ncr_summary(row)

    async def create_discrepancy(
        self, s: AsyncSession, *, actor_user_id: UUID, data: DiscrepancyCreate
    ) -> DiscrepancySummary:
        await self._require(s, actor_user_id, "quality.discrepancy.create", data.project_id)
        now = datetime.now(UTC)
        row = DiscrepancyCase(
            id=uuid4(),
            project_id=data.project_id,
            quantity_item_id=data.quantity_item_id,
            description=data.description,
            evidence_ref=None,
            evidence_document_id=data.evidence_document_id,
            proposed_resolution=None,
            resolved_by=None,
            resolved_at=None,
            status="open",
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
            "quality",
            "discrepancy_cases",
            row.id,
            "create",
            None,
            {
                "project_id": str(row.project_id),
                "quantity_item_id": str(row.quantity_item_id),
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "status": "open",
                "version": 1,
            },
        )
        return discrepancy_summary(row)

    async def transition_discrepancy(
        self, s: AsyncSession, *, actor_user_id: UUID, case_id: UUID, data: DiscrepancyTransition
    ) -> DiscrepancySummary:
        row = await s.get(DiscrepancyCase, case_id)
        if row is None:
            raise ChangeControlNotFoundError(f"discrepancy {case_id} does not exist")
        await self._require(
            s,
            actor_user_id,
            "quality.discrepancy.resolve"
            if data.target_status == "resolved"
            else "quality.discrepancy.transition",
            row.project_id,
        )
        if data.target_status not in DISCREPANCY_TRANSITIONS.get(row.status, frozenset()):
            raise ChangeControlConflictError(
                f"discrepancy cannot move from {row.status} to {data.target_status}"
            )
        if data.target_status == "explanation_provided" and not data.proposed_resolution:
            raise ChangeControlConflictError("explanation and proposed resolution are required")
        if (
            data.target_status == "resolved"
            and row.evidence_document_id is None
            and data.evidence_document_id is None
        ):
            raise ChangeControlConflictError("resolution requires controlled evidence")
        before = {"status": row.status, "version": row.version}
        row.status = data.target_status
        if data.proposed_resolution:
            row.proposed_resolution = data.proposed_resolution
        if data.evidence_document_id:
            row.evidence_document_id = data.evidence_document_id
        if data.target_status == "resolved":
            row.resolved_by = actor_user_id
            row.resolved_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await s.flush()
        await self._audit(
            s,
            actor_user_id,
            "quality",
            "discrepancy_cases",
            row.id,
            "transition",
            before,
            {
                "status": row.status,
                "resolution_recorded": row.proposed_resolution is not None,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "resolved_by": str(row.resolved_by) if row.resolved_by else None,
                "version": row.version,
            },
        )
        return discrepancy_summary(row)
