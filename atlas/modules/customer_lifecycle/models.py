"""ORM mappings onto canonical Phase 8 customer tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class AuditColumns:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Booking(AuditColumns, Base):
    __tablename__ = "bookings"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    lead_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    booking_date: Mapped[date] = mapped_column(Date)
    booking_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str]


class PaymentPlan(AuditColumns, Base):
    __tablename__ = "payment_plans"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    plan_name: Mapped[str | None]
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    status: Mapped[str]


class Installment(AuditColumns, Base):
    __tablename__ = "payment_plan_installments"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    payment_plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str]


class Collection(AuditColumns, Base):
    __tablename__ = "collections"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    installment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    received_date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str | None]
    reference_number: Mapped[str | None]
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    received_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str]


class Registration(AuditColumns, Base):
    __tablename__ = "registration_records"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    registration_date: Mapped[date | None] = mapped_column(Date)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    registered_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str]


class Possession(AuditColumns, Base):
    __tablename__ = "possession_records"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    handover_date: Mapped[date | None] = mapped_column(Date)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    handed_over_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str]


class BookingContract(Base):
    __tablename__ = "booking_contracts"
    __table_args__ = {"schema": "customers"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    booking_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    executed_document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    linked_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
