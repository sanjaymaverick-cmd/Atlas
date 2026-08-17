"""Audited Phase 5 construction, quality, snag, and EHS workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.construction.contracts import (
    ConstructionConflictError,
    ConstructionNotAuthorisedError,
    ConstructionNotFoundError,
)
from atlas.modules.construction.models import (
    EhsIncident,
    Inspection,
    InspectionEvidence,
    InspectionTemplate,
    ProgressUpdate,
    ScheduleActivity,
    SiteDiaryEntry,
    SnagItem,
)
from atlas.modules.construction.schemas import (
    EhsCreate,
    EhsSummary,
    InspectionCompletion,
    InspectionCreate,
    InspectionSummary,
    ProgressCreate,
    ProgressSummary,
    ScheduleCreate,
    ScheduleSummary,
    SiteDiaryCreate,
    SiteDiarySummary,
    SnagCreate,
    SnagSummary,
    TemplateCreate,
    TemplateSummary,
)
from atlas.modules.identity.contracts import IdentityContract
from atlas.platform.audit.writer import record_event

ACTIVITY_TRANSITIONS = {
    "not_started": frozenset({"in_progress", "delayed"}),
    "in_progress": frozenset({"delayed", "completed"}),
    "delayed": frozenset({"in_progress", "completed"}),
}
EHS_TRANSITIONS = {
    "open": frozenset({"corrective_action_assigned"}),
    "corrective_action_assigned": frozenset({"closed"}),
}
TEMPLATE_TRANSITIONS = {"draft": frozenset({"active", "retired"}), "active": frozenset({"retired"})}
SNAG_TRANSITIONS = {
    "open": frozenset({"assigned"}),
    "assigned": frozenset({"rectified"}),
    "rectified": frozenset({"verified", "assigned"}),
    "verified": frozenset({"closed", "assigned"}),
}


def activity_summary(r: ScheduleActivity) -> ScheduleSummary:
    return ScheduleSummary(
        r.id,
        r.project_id,
        r.name,
        r.planned_start,
        r.planned_end,
        r.actual_start,
        r.actual_end,
        r.status,
        r.version,
        r.archived_at,
    )


def diary_summary(r: SiteDiaryEntry) -> SiteDiarySummary:
    return SiteDiarySummary(
        r.id, r.project_id, r.entry_date, r.client_record_id, r.status, r.version, r.archived_at
    )


def progress_summary(r: ProgressUpdate) -> ProgressSummary:
    return ProgressSummary(
        r.id,
        r.project_id,
        r.schedule_activity_id,
        r.progress_date,
        r.percent_complete,
        r.evidence_document_id,
        r.version,
        r.archived_at,
    )


def ehs_summary(r: EhsIncident) -> EhsSummary:
    return EhsSummary(
        r.id, r.project_id, r.incident_date, r.severity, r.status, r.version, r.archived_at
    )


def template_summary(r: InspectionTemplate) -> TemplateSummary:
    return TemplateSummary(
        r.id, r.project_id, r.work_package, r.template_name, r.status, r.version, r.archived_at
    )


def inspection_summary(r: Inspection) -> InspectionSummary:
    return InspectionSummary(
        r.id,
        r.project_id,
        r.template_id,
        r.inspector_id,
        r.result,
        r.status,
        r.version,
        r.archived_at,
    )


def snag_summary(r: SnagItem) -> SnagSummary:
    return SnagSummary(
        r.id,
        r.project_id,
        r.description,
        r.severity,
        r.assigned_to,
        r.due_date,
        r.evidence_document_id,
        r.status,
        r.version,
        r.archived_at,
    )


class ConstructionService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def _require(
        self, session: AsyncSession, *, actor: UUID, permission: str, project_id: UUID | None
    ) -> None:
        if not await self._identity.check_scoped_role(
            session, user_id=actor, permission_code=permission, project_id=project_id
        ):
            raise ConstructionNotAuthorisedError(
                f"user may not {permission} in the requested scope"
            )

    async def _audit(
        self,
        session: AsyncSession,
        *,
        actor: UUID,
        schema: str,
        table: str,
        row_id: UUID,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
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

    async def create_activity(
        self, session: AsyncSession, *, actor_user_id: UUID, data: ScheduleCreate
    ) -> ScheduleSummary:
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.schedule.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = ScheduleActivity(
            id=uuid4(),
            project_id=data.project_id,
            wbs_reference=data.wbs_reference,
            name=data.name,
            planned_start=data.planned_start,
            planned_end=data.planned_end,
            actual_start=None,
            actual_end=None,
            predecessor_activity_id=data.predecessor_activity_id,
            status="not_started",
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
            schema="construction",
            table="schedule_activities",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "name": row.name,
                "planned_start": row.planned_start,
                "planned_end": row.planned_end,
                "status": row.status,
                "version": 1,
            },
        )
        return activity_summary(row)

    async def transition_activity(
        self, session: AsyncSession, *, actor_user_id: UUID, activity_id: UUID, target_status: str
    ) -> ScheduleSummary:
        row = await session.get(ScheduleActivity, activity_id)
        if row is None:
            raise ConstructionNotFoundError(f"activity {activity_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.schedule.update",
            project_id=row.project_id,
        )
        if target_status not in ACTIVITY_TRANSITIONS.get(row.status, frozenset()):
            raise ConstructionConflictError(
                f"activity cannot move from {row.status} to {target_status}"
            )
        before = {"status": row.status, "version": row.version}
        today = datetime.now(UTC).date()
        row.status = target_status
        if target_status == "in_progress" and row.actual_start is None:
            row.actual_start = today
        if target_status == "completed":
            row.actual_end = today
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="construction",
            table="schedule_activities",
            row_id=row.id,
            action="transition",
            before=before,
            after={
                "status": row.status,
                "actual_start": row.actual_start,
                "actual_end": row.actual_end,
                "version": row.version,
            },
        )
        return activity_summary(row)

    async def add_progress(
        self, session: AsyncSession, *, actor_user_id: UUID, activity_id: UUID, data: ProgressCreate
    ) -> ProgressSummary:
        activity = await session.get(ScheduleActivity, activity_id)
        if activity is None:
            raise ConstructionNotFoundError(f"activity {activity_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.progress.create",
            project_id=activity.project_id,
        )
        latest = await session.scalar(
            select(ProgressUpdate)
            .where(
                ProgressUpdate.schedule_activity_id == activity_id,
                ProgressUpdate.archived_at.is_(None),
            )
            .order_by(ProgressUpdate.progress_date.desc())
            .limit(1)
        )
        if latest is not None and data.percent_complete < latest.percent_complete:
            raise ConstructionConflictError("progress percentage may not decrease")
        now = datetime.now(UTC)
        row = ProgressUpdate(
            id=uuid4(),
            project_id=activity.project_id,
            schedule_activity_id=activity_id,
            progress_date=data.progress_date,
            percent_complete=data.percent_complete,
            notes=data.notes,
            evidence_document_id=data.evidence_document_id,
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
            raise ConstructionConflictError(
                "activity already has a progress update for this date"
            ) from exc
        await self._audit(
            session,
            actor=actor_user_id,
            schema="construction",
            table="progress_updates",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "schedule_activity_id": str(activity_id),
                "progress_date": row.progress_date,
                "percent_complete": row.percent_complete,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "version": 1,
            },
        )
        return progress_summary(row)

    async def submit_site_diary(
        self, session: AsyncSession, *, actor_user_id: UUID, data: SiteDiaryCreate
    ) -> SiteDiarySummary:
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.diary.submit",
            project_id=data.project_id,
        )
        existing = await session.scalar(
            select(SiteDiaryEntry).where(
                SiteDiaryEntry.project_id == data.project_id,
                SiteDiaryEntry.client_record_id == data.client_record_id,
            )
        )
        if existing is not None:
            if existing.entry_date != data.entry_date:
                raise ConstructionConflictError(
                    "client record ID was already used for another diary date"
                )
            return diary_summary(existing)
        now = datetime.now(UTC)

        def movements(values: tuple[Any, ...]) -> list[dict[str, str]]:
            return [
                {"material_id": str(v.material_id), "quantity": str(v.quantity), "unit": v.unit}
                for v in values
            ]

        row = SiteDiaryEntry(
            id=uuid4(),
            project_id=data.project_id,
            entry_date=data.entry_date,
            client_record_id=data.client_record_id,
            device_recorded_at=data.device_recorded_at,
            weather=data.weather,
            labour_strength=dict(data.labour_strength),
            materials_received=movements(data.materials_received),
            materials_consumed=movements(data.materials_consumed),
            equipment_breakdowns=data.equipment_breakdowns,
            visitor_log=[{"count": data.visitor_count}],
            site_instructions=data.site_instructions,
            delays_and_reasons=data.delays_and_reasons,
            recorded_by=actor_user_id,
            status="submitted",
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
            raise ConstructionConflictError(
                "site diary conflicts with an existing project date or client record"
            ) from exc
        await self._audit(
            session,
            actor=actor_user_id,
            schema="construction",
            table="site_diary_entries",
            row_id=row.id,
            action="submit",
            before=None,
            after={
                "project_id": str(row.project_id),
                "entry_date": row.entry_date,
                "client_record_id": str(row.client_record_id),
                "labour_category_count": len(data.labour_strength),
                "received_item_count": len(data.materials_received),
                "consumed_item_count": len(data.materials_consumed),
                "visitor_count": data.visitor_count,
                "status": row.status,
                "version": 1,
            },
        )
        return diary_summary(row)

    async def create_ehs_incident(
        self, session: AsyncSession, *, actor_user_id: UUID, data: EhsCreate
    ) -> EhsSummary:
        if data.severity not in {"minor", "major", "fatal"}:
            raise ConstructionConflictError("EHS severity must be minor, major, or fatal")
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.ehs.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = EhsIncident(
            id=uuid4(),
            project_id=data.project_id,
            site_diary_entry_id=data.site_diary_entry_id,
            incident_date=data.incident_date,
            severity=data.severity,
            description=data.description,
            corrective_action=None,
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
        await self._audit(
            session,
            actor=actor_user_id,
            schema="construction",
            table="ehs_incidents",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "site_diary_entry_id": str(row.site_diary_entry_id)
                if row.site_diary_entry_id
                else None,
                "incident_date": row.incident_date,
                "severity": row.severity,
                "status": row.status,
                "version": 1,
            },
        )
        return ehs_summary(row)

    async def transition_ehs_incident(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        incident_id: UUID,
        target_status: str,
        corrective_action: str | None = None,
    ) -> EhsSummary:
        row = await session.get(EhsIncident, incident_id)
        if row is None:
            raise ConstructionNotFoundError(f"EHS incident {incident_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="construction.ehs.close"
            if target_status == "closed"
            else "construction.ehs.update",
            project_id=row.project_id,
        )
        if target_status not in EHS_TRANSITIONS.get(row.status, frozenset()):
            raise ConstructionConflictError(
                f"EHS incident cannot move from {row.status} to {target_status}"
            )
        if target_status == "corrective_action_assigned" and not corrective_action:
            raise ConstructionConflictError("corrective action is required")
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        if corrective_action:
            row.corrective_action = corrective_action
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="construction",
            table="ehs_incidents",
            row_id=row.id,
            action="transition",
            before=before,
            after={
                "severity": row.severity,
                "status": row.status,
                "corrective_action_recorded": row.corrective_action is not None,
                "version": row.version,
            },
        )
        return ehs_summary(row)

    async def create_template(
        self, session: AsyncSession, *, actor_user_id: UUID, data: TemplateCreate
    ) -> TemplateSummary:
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.template.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        checklist = [
            {"item": i.item, "requires_evidence": i.requires_evidence} for i in data.checklist
        ]
        if not checklist:
            raise ConstructionConflictError("inspection template requires at least one item")
        row = InspectionTemplate(
            id=uuid4(),
            project_id=data.project_id,
            work_package=data.work_package,
            template_name=data.template_name,
            checklist=checklist,
            status="draft",
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
            raise ConstructionConflictError(
                "template name already exists in this project scope"
            ) from exc
        await self._audit(
            session,
            actor=actor_user_id,
            schema="quality",
            table="inspection_templates",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id) if row.project_id else None,
                "work_package": row.work_package,
                "template_name": row.template_name,
                "checklist_item_count": len(checklist),
                "status": row.status,
                "version": 1,
            },
        )
        return template_summary(row)

    async def transition_template(
        self, session: AsyncSession, *, actor_user_id: UUID, template_id: UUID, target_status: str
    ) -> TemplateSummary:
        row = await session.get(InspectionTemplate, template_id)
        if row is None:
            raise ConstructionNotFoundError(f"template {template_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.template.update",
            project_id=row.project_id,
        )
        if target_status not in TEMPLATE_TRANSITIONS.get(row.status, frozenset()):
            raise ConstructionConflictError(
                f"template cannot move from {row.status} to {target_status}"
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
            schema="quality",
            table="inspection_templates",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return template_summary(row)

    async def schedule_inspection(
        self, session: AsyncSession, *, actor_user_id: UUID, data: InspectionCreate
    ) -> InspectionSummary:
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.inspection.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        row = Inspection(
            id=uuid4(),
            project_id=data.project_id,
            building_id=data.building_id,
            floor_id=data.floor_id,
            unit_id=data.unit_id,
            template_id=data.template_id,
            inspector_id=data.inspector_id,
            result="pending",
            photos_ref=None,
            notes=None,
            status="scheduled",
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
            schema="quality",
            table="inspections",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "template_id": str(row.template_id) if row.template_id else None,
                "inspector_id": str(row.inspector_id) if row.inspector_id else None,
                "status": row.status,
                "version": 1,
            },
        )
        return inspection_summary(row)

    async def complete_inspection(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        inspection_id: UUID,
        data: InspectionCompletion,
    ) -> InspectionSummary:
        row = await session.get(Inspection, inspection_id)
        if row is None:
            raise ConstructionNotFoundError(f"inspection {inspection_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.inspection.complete",
            project_id=row.project_id,
        )
        if row.status == "completed":
            raise ConstructionConflictError("inspection result is final")
        if data.result not in {"pass", "fail"}:
            raise ConstructionConflictError("inspection result must be pass or fail")
        if row.inspector_id is not None and row.inspector_id != actor_user_id:
            raise ConstructionNotAuthorisedError("only assigned inspector may complete inspection")
        before = {"result": row.result, "status": row.status, "version": row.version}
        row.result = data.result
        row.notes = data.notes
        row.status = "completed"
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        for document_id in dict.fromkeys(data.evidence_document_ids):
            session.add(
                InspectionEvidence(
                    id=uuid4(),
                    inspection_id=row.id,
                    document_id=document_id,
                    evidence_type="photo",
                    created_at=datetime.now(UTC),
                    created_by=actor_user_id,
                )
            )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConstructionConflictError("inspection evidence is duplicated") from exc
        await self._audit(
            session,
            actor=actor_user_id,
            schema="quality",
            table="inspections",
            row_id=row.id,
            action="complete",
            before=before,
            after={
                "result": row.result,
                "status": row.status,
                "evidence_count": len(set(data.evidence_document_ids)),
                "version": row.version,
            },
        )
        return inspection_summary(row)

    async def create_snag(
        self, session: AsyncSession, *, actor_user_id: UUID, data: SnagCreate
    ) -> SnagSummary:
        if data.severity not in {"minor", "major", "critical"}:
            raise ConstructionConflictError("snag severity must be minor, major, or critical")
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.snag.create",
            project_id=data.project_id,
        )
        now = datetime.now(UTC)
        status = "assigned" if data.assigned_to else "open"
        row = SnagItem(
            id=uuid4(),
            project_id=data.project_id,
            inspection_id=data.inspection_id,
            building_id=data.building_id,
            floor_id=data.floor_id,
            unit_id=data.unit_id,
            description=data.description,
            severity=data.severity,
            assigned_to=data.assigned_to,
            due_date=data.due_date,
            evidence_document_id=data.evidence_document_id,
            status=status,
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
            schema="quality",
            table="snag_items",
            row_id=row.id,
            action="create",
            before=None,
            after={
                "project_id": str(row.project_id),
                "inspection_id": str(row.inspection_id) if row.inspection_id else None,
                "severity": row.severity,
                "assigned_to": str(row.assigned_to) if row.assigned_to else None,
                "due_date": row.due_date,
                "evidence_document_id": str(row.evidence_document_id)
                if row.evidence_document_id
                else None,
                "status": row.status,
                "version": 1,
            },
        )
        return snag_summary(row)

    async def transition_snag(
        self, session: AsyncSession, *, actor_user_id: UUID, snag_id: UUID, target_status: str
    ) -> SnagSummary:
        row = await session.get(SnagItem, snag_id)
        if row is None:
            raise ConstructionNotFoundError(f"snag {snag_id} does not exist")
        await self._require(
            session,
            actor=actor_user_id,
            permission="quality.snag.verify"
            if target_status in {"verified", "closed"}
            else "quality.snag.update",
            project_id=row.project_id,
        )
        if target_status not in SNAG_TRANSITIONS.get(row.status, frozenset()):
            raise ConstructionConflictError(
                f"snag cannot move from {row.status} to {target_status}"
            )
        if target_status == "assigned" and row.assigned_to is None:
            raise ConstructionConflictError("snag requires an assignee")
        before = {"status": row.status, "version": row.version}
        row.status = target_status
        row.updated_at = datetime.now(UTC)
        row.updated_by = actor_user_id
        row.version += 1
        await session.flush()
        await self._audit(
            session,
            actor=actor_user_id,
            schema="quality",
            table="snag_items",
            row_id=row.id,
            action="transition",
            before=before,
            after={"status": row.status, "version": row.version},
        )
        return snag_summary(row)
