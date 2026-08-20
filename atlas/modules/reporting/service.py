"""Read-only Phase 10 analytics and audited report requests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.reporting.contracts import (
    ReportingConflictError,
    ReportingNotAuthorisedError,
    ReportingNotFoundError,
)
from atlas.modules.reporting.models import ProjectSummaryView, ReportRequest
from atlas.modules.reporting.schemas import (
    EntityDashboard,
    ProjectDashboard,
    ReportRequestCreate,
    ReportRequestSummary,
)
from atlas.platform.audit.writer import record_event


def project_dto(r: ProjectSummaryView) -> ProjectDashboard:
    return ProjectDashboard(
        r.project_id,
        r.legal_entity_id,
        r.planned_amount,
        r.committed_amount,
        r.actual_amount,
        r.approved_po_amount,
        r.released_payment_amount,
        r.allocated_collection_amount,
        r.outstanding_receivable_amount,
        r.unallocated_collection_count,
        r.overdue_installment_count,
        r.delayed_activity_count,
        r.failed_inspection_count,
        r.open_compliance_count,
        r.open_reconciliation_count,
        r.total_unit_count,
        r.available_unit_count,
        r.committed_unit_count,
        r.refreshed_at,
    )


class ReportingService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(
        self,
        s: AsyncSession,
        actor: UUID,
        permission: str,
        *,
        entity: UUID | None = None,
        project: UUID | None = None,
    ) -> None:
        if not await self._identity.check_scoped_role(
            s, user_id=actor, permission_code=permission, legal_entity_id=entity, project_id=project
        ):
            raise ReportingNotAuthorisedError(f"user may not {permission} in requested scope")

    async def get_project_dashboard(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
    ) -> ProjectDashboard:
        await self._require(primary, actor_user_id, "reporting.dashboard.read", project=project_id)
        row = await reporting.get(ProjectSummaryView, project_id)
        if row is None:
            raise ReportingNotFoundError(
                f"reporting summary for project {project_id} does not exist"
            )
        return project_dto(row)

    async def get_entity_dashboard(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        legal_entity_id: UUID,
    ) -> EntityDashboard:
        await self._require(
            primary, actor_user_id, "reporting.dashboard.read", entity=legal_entity_id
        )
        rows = list(
            (
                await reporting.scalars(
                    select(ProjectSummaryView).where(
                        ProjectSummaryView.legal_entity_id == legal_entity_id
                    )
                )
            ).all()
        )
        if not rows:
            raise ReportingNotFoundError(
                f"reporting summary for legal entity {legal_entity_id} does not exist"
            )
        return EntityDashboard(
            legal_entity_id,
            len(rows),
            sum((r.planned_amount for r in rows), Decimal()),
            sum((r.committed_amount for r in rows), Decimal()),
            sum((r.actual_amount for r in rows), Decimal()),
            sum((r.released_payment_amount for r in rows), Decimal()),
            sum((r.allocated_collection_amount for r in rows), Decimal()),
            sum((r.outstanding_receivable_amount for r in rows), Decimal()),
            sum(r.delayed_activity_count for r in rows),
            sum(r.failed_inspection_count for r in rows),
            sum(r.open_compliance_count for r in rows),
            sum(r.available_unit_count for r in rows),
            max(r.refreshed_at for r in rows),
        )

    async def create_report_request(
        self,
        primary: AsyncSession,
        reporting: AsyncSession,
        *,
        actor_user_id: UUID,
        data: ReportRequestCreate,
    ) -> ReportRequestSummary:
        await self._require(
            primary,
            actor_user_id,
            "reporting.report.request",
            entity=data.legal_entity_id,
            project=data.project_id,
        )
        if data.report_type not in {
            "ceo_project_summary",
            "ceo_entity_summary",
        } or data.output_format not in {"pdf", "xlsx"}:
            raise ReportingConflictError("report request type or format is invalid")
        if data.report_type == "ceo_project_summary":
            if data.project_id is None:
                raise ReportingConflictError("project report requires project scope")
            source = await reporting.get(ProjectSummaryView, data.project_id)
            if source is None or source.legal_entity_id != data.legal_entity_id:
                raise ReportingConflictError("project does not belong to reporting legal entity")
        elif data.project_id is not None:
            raise ReportingConflictError("entity report may not include project scope")
        now = datetime.now(UTC)
        row = ReportRequest(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            project_id=data.project_id,
            report_type=data.report_type,
            output_format=data.output_format,
            status="queued",
            output_document_id=None,
            requested_by=actor_user_id,
            requested_at=now,
            completed_at=None,
            expires_at=None,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        primary.add(row)
        await primary.flush()
        await record_event(
            primary,
            actor_user_id=actor_user_id,
            entity_schema="reporting",
            entity_table="report_requests",
            entity_id=row.id,
            action="create",
            before_state=None,
            after_state={
                "legal_entity_id": str(row.legal_entity_id),
                "project_id": str(row.project_id) if row.project_id else None,
                "report_type": row.report_type,
                "output_format": row.output_format,
                "status": row.status,
                "version": 1,
            },
        )
        return ReportRequestSummary(
            row.id,
            row.legal_entity_id,
            row.project_id,
            row.report_type,
            row.output_format,
            row.status,
            row.requested_at,
            row.version,
        )
