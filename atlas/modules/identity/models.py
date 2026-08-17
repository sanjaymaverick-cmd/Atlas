"""ORM mappings onto the ``identity`` schema.

Private to this module — `.importlinter` blocks imports from outside.

These describe `db/schema.sql`; they do not define it. Columns are mapped
explicitly rather than reflected so that a drift between this file and the
canonical DDL shows up as a failing test, and no ``metadata.create_all`` path
exists anywhere: the schema is created by Alembic, from schema.sql.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    business_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    full_name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    phone: Mapped[str | None] = mapped_column(String)
    is_owner: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(String)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str | None] = mapped_column(String)


class UserRole(Base):
    """A role assignment, optionally narrowed to an entity and/or project.

    The meaning of the two nullable scope columns is defined once, in
    ``scoping.py``. Nothing should interpret them inline.
    """

    __tablename__ = "user_roles"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.users.id"))
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.roles.id"))
    legal_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    granted_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class Device(Base):
    """A passkey-bound device.

    ``sign_counter`` is the WebAuthn signature counter. It must increase on
    every assertion; a stalled or decreasing counter indicates a cloned
    authenticator. See ``webauthn_adapter.py``.
    """

    __tablename__ = "devices"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.users.id"))
    device_name: Mapped[str | None] = mapped_column(String)
    passkey_credential_id: Mapped[str] = mapped_column(String, unique=True)
    public_key: Mapped[str] = mapped_column(String)
    sign_counter: Mapped[int]
    trust_level: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enrolled_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Session(Base):
    """A short-lived, server-revocable session.

    ``session_token_hash`` holds a hash, never the token: a database read must
    not yield anything usable to impersonate the session.
    """

    __tablename__ = "sessions"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.users.id"))
    device_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("identity.devices.id"))
    session_token_hash: Mapped[str] = mapped_column(String)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    step_up_verified: Mapped[bool] = mapped_column(Boolean)
    step_up_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BreakGlassCredential(Base):
    """Blueprint §3.2.

    ``sealed_reference`` is a pointer to physically-secured material — an
    envelope location, a safe deposit reference — and never the credential
    itself. Storing the secret here would defeat the purpose of sealing it
    outside the system the credential exists to recover.
    """

    __tablename__ = "break_glass_credentials"
    __table_args__ = {"schema": "identity"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    holder_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.users.id")
    )
    purpose: Mapped[str] = mapped_column(String)
    sealed_reference: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_invoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String)
