"""Organization service — legal entities and projects.

Two properties hold for every mutation here, and both are Blueprint §2
principles rather than conveniences:

*Every mutating action writes an audit event, in the same transaction.* An
audit log missing an event that happened is as bad as one containing an event
that did not, so the event and the change commit together or neither does.

*No silent overwrites.* Updates increment ``version`` and record the prior
values in the audit event's ``before_state``. Deletes do not exist: a project
is archived by setting ``archived_at``, so the row and its history survive.

Authorisation is not decided here. The service asks Identity's contract
whether the caller holds a role reaching this legal entity and project, and
Identity answers — which is what keeps §2's separation rules in one place.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.contracts import IdentityContract
from atlas.modules.organization.contracts import ConflictError, NotAuthorisedError, NotFoundError
from atlas.modules.organization.models import LegalEntity, Project
from atlas.modules.organization.schemas import (
    LegalEntitySummary,
    ProjectCreate,
    ProjectSummary,
    ProjectUpdate,
)
from atlas.platform.audit.writer import record_event

PERM_PROJECT_CREATE = "project.create"
PERM_PROJECT_UPDATE = "project.update"
PERM_PROJECT_ARCHIVE = "project.archive"
PERM_PROJECT_READ = "project.read"


def _project_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        legal_entity_id=project.legal_entity_id,
        name=project.name,
        code=project.code,
        city=project.city,
        status=project.status,
        start_date=project.start_date,
        target_completion_date=project.target_completion_date,
        version=project.version,
        archived_at=project.archived_at,
    )


def _auditable(project: Project) -> dict[str, Any]:
    """The project's state, as recorded in an audit event."""
    return {
        "id": str(project.id),
        "legal_entity_id": str(project.legal_entity_id),
        "name": project.name,
        "code": project.code,
        "city": project.city,
        "status": project.status,
        "start_date": project.start_date,
        "target_completion_date": project.target_completion_date,
        "version": project.version,
        "archived_at": project.archived_at,
    }


class OrganizationService:
    def __init__(self, identity: IdentityContract) -> None:
        self._identity = identity

    async def unit_belongs_to_project(
        self, session: AsyncSession, *, unit_id: UUID, project_id: UUID
    ) -> bool:
        value = await session.scalar(
            text(
                """SELECT EXISTS (
                SELECT 1 FROM organization.units u
                JOIN organization.floors f ON f.id = u.floor_id
                JOIN organization.buildings b ON b.id = f.building_id
                WHERE u.id = :unit_id AND b.project_id = :project_id
                )"""
            ),
            {"unit_id": unit_id, "project_id": project_id},
        )
        return bool(value)

    # -- authorisation ----------------------------------------------------

    async def _require(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        permission: str,
        legal_entity_id: UUID | None,
        project_id: UUID | None,
    ) -> None:
        allowed = await self._identity.check_scoped_role(
            session,
            user_id=actor_user_id,
            permission_code=permission,
            legal_entity_id=legal_entity_id,
            project_id=project_id,
        )
        if not allowed:
            raise NotAuthorisedError(
                f"user {actor_user_id} may not {permission} in "
                f"legal_entity={legal_entity_id} project={project_id}"
            )

    # -- reads ------------------------------------------------------------

    async def get_project(
        self, session: AsyncSession, *, actor_user_id: UUID, project_id: UUID
    ) -> ProjectSummary:
        project = await session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"project {project_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_PROJECT_READ,
            legal_entity_id=project.legal_entity_id,
            project_id=project.id,
        )
        return _project_summary(project)

    async def get_legal_entity(
        self, session: AsyncSession, *, legal_entity_id: UUID
    ) -> LegalEntitySummary:
        entity = await session.get(LegalEntity, legal_entity_id)
        if entity is None:
            raise NotFoundError(f"legal entity {legal_entity_id} does not exist")
        return LegalEntitySummary(
            id=entity.id,
            business_group_id=entity.business_group_id,
            name=entity.name,
            registration_number=entity.registration_number,
            entity_type=entity.entity_type,
            status=entity.status,
            version=entity.version,
        )

    async def list_projects(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        legal_entity_id: UUID,
    ) -> list[ProjectSummary]:
        """Live projects in an entity. Archived ones are excluded."""
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_PROJECT_READ,
            legal_entity_id=legal_entity_id,
            project_id=None,
        )
        if await session.get(LegalEntity, legal_entity_id) is None:
            raise NotFoundError(f"legal entity {legal_entity_id} does not exist")
        result = await session.execute(
            select(Project)
            .where(Project.legal_entity_id == legal_entity_id)
            .where(Project.archived_at.is_(None))
            .order_by(Project.code)
        )
        return [_project_summary(p) for p in result.scalars()]

    # -- mutations --------------------------------------------------------

    async def create_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        data: ProjectCreate,
    ) -> ProjectSummary:
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_PROJECT_CREATE,
            legal_entity_id=data.legal_entity_id,
            project_id=None,
        )
        if await session.get(LegalEntity, data.legal_entity_id) is None:
            raise NotFoundError(f"legal entity {data.legal_entity_id} does not exist")

        now = datetime.now(UTC)
        project = Project(
            id=uuid4(),
            legal_entity_id=data.legal_entity_id,
            name=data.name,
            code=data.code,
            city=data.city,
            status=data.status,
            start_date=data.start_date,
            target_completion_date=data.target_completion_date,
            created_at=now,
            updated_at=now,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            version=1,
            archived_at=None,
        )
        session.add(project)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("a project with this code already exists") from exc

        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="organization",
            entity_table="projects",
            entity_id=project.id,
            action="create",
            after_state=_auditable(project),
        )
        return _project_summary(project)

    async def update_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
        data: ProjectUpdate,
    ) -> ProjectSummary:
        project = await session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"project {project_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_PROJECT_UPDATE,
            legal_entity_id=project.legal_entity_id,
            project_id=project.id,
        )
        if project.archived_at is not None:
            raise NotAuthorisedError(
                f"project {project_id} is archived; unarchive it before editing"
            )

        before = _auditable(project)

        changes = {k: v for k, v in asdict(data).items() if v is not None}
        for field, value in changes.items():
            setattr(project, field, value)
        project.version += 1
        project.updated_by = actor_user_id
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("the project update conflicts with an existing record") from exc

        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="organization",
            entity_table="projects",
            entity_id=project.id,
            action="update",
            before_state=before,
            after_state=_auditable(project),
        )
        return _project_summary(project)

    async def archive_project(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        project_id: UUID,
    ) -> ProjectSummary:
        """Archive a project.

        This is the only removal there is. Deleting the row would take its
        history with it, which §2 forbids.
        """
        project = await session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"project {project_id} does not exist")
        await self._require(
            session,
            actor_user_id=actor_user_id,
            permission=PERM_PROJECT_ARCHIVE,
            legal_entity_id=project.legal_entity_id,
            project_id=project.id,
        )
        if project.archived_at is not None:
            return _project_summary(project)

        before = _auditable(project)
        project.archived_at = datetime.now(UTC)
        project.version += 1
        project.updated_by = actor_user_id
        await session.flush()

        await record_event(
            session,
            actor_user_id=actor_user_id,
            entity_schema="organization",
            entity_table="projects",
            entity_id=project.id,
            action="archive",
            before_state=before,
            after_state=_auditable(project),
        )
        return _project_summary(project)
