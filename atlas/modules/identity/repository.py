"""Identity queries.

Private to this module. Nothing outside Identity may import this — the point
of the boundary is that other modules cannot construct their own view of who
may do what.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.modules.identity.models import (
    Device,
    Permission,
    Role,
    Session,
    User,
    UserRole,
)
from atlas.modules.identity.scoping import RoleGrant


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_session_with_context(
    session: AsyncSession, session_id: UUID
) -> tuple[Session, User, Device] | None:
    """Fetch a session together with its user and device.

    One query rather than three: the access check needs all three on every
    request, and issuing them separately would triple the per-request cost of
    the hot path.
    """
    result = await session.execute(
        select(Session, User, Device)
        .join(User, Session.user_id == User.id)
        .join(Device, Session.device_id == Device.id)
        .where(Session.id == session_id)
    )
    row = result.one_or_none()
    return (row[0], row[1], row[2]) if row is not None else None


async def get_session_by_token_hash(session: AsyncSession, token_hash: str) -> Session | None:
    result = await session.execute(select(Session).where(Session.session_token_hash == token_hash))
    return result.scalar_one_or_none()


async def load_grants(session: AsyncSession, user_id: UUID) -> list[RoleGrant]:
    """Every permission the user holds, with the scope each was granted in.

    Returns one ``RoleGrant`` per (permission, scope) pair — a role carrying
    three permissions granted on two projects yields six. Interpreting them is
    ``scoping.py``'s job; this function only reads.
    """
    result = await session.execute(
        select(
            Permission.code,
            UserRole.legal_entity_id,
            UserRole.project_id,
        )
        .select_from(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .join(
            # role_permissions has no mapped class; it is a pure join table.
            Role.metadata.tables["identity.role_permissions"],
            Role.id == Role.metadata.tables["identity.role_permissions"].c.role_id,
        )
        .join(
            Permission,
            Permission.id == Role.metadata.tables["identity.role_permissions"].c.permission_id,
        )
        .where(UserRole.user_id == user_id)
    )
    return [
        RoleGrant(permission_code=code, legal_entity_id=entity_id, project_id=project_id)
        for code, entity_id, project_id in result.all()
    ]


async def get_device(session: AsyncSession, device_id: UUID) -> Device | None:
    return await session.get(Device, device_id)


async def get_device_by_credential_id(session: AsyncSession, credential_id: str) -> Device | None:
    result = await session.execute(
        select(Device).where(Device.passkey_credential_id == credential_id)
    )
    return result.scalar_one_or_none()


async def list_devices_by_status(session: AsyncSession, status: str) -> list[Device]:
    result = await session.execute(
        select(Device).where(Device.status == status).order_by(Device.enrolled_at)
    )
    return list(result.scalars())


async def get_project_entity_id(session: AsyncSession, project_id: UUID) -> UUID | None:
    """The legal entity a project belongs to.

    Identity needs this to decide whether an entity-scoped grant covers a
    project, but must not import Organization's models — that would make the
    module graph cyclic. A narrow read of one column through raw SQL is the
    lesser evil, and is confined to this one function.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT legal_entity_id FROM organization.projects WHERE id = :id"),
        {"id": project_id},
    )
    row = result.one_or_none()
    return row[0] if row is not None else None
