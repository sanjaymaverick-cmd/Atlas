"""ORM mappings onto the canonical ``land`` schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atlas.platform.db import Base


class LandParcel(Base):
    __tablename__ = "land_parcels"
    __table_args__ = {"schema": "land"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    survey_number: Mapped[str | None] = mapped_column(String)
    area_sqft: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    location: Mapped[str | None] = mapped_column(String)
    acquisition_status: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LandLegalApproval(Base):
    __tablename__ = "land_legal_approvals"
    __table_args__ = {"schema": "land"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    land_parcel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    approval_type: Mapped[str] = mapped_column(String)
    authority: Mapped[str | None] = mapped_column(String)
    reference_number: Mapped[str | None] = mapped_column(String)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DueDiligenceItem(Base):
    __tablename__ = "due_diligence_items"
    __table_args__ = {"schema": "land"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    land_parcel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("land.land_parcels.id")
    )
    category: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    result: Mapped[str] = mapped_column(String)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoanObligation(Base):
    __tablename__ = "loan_obligations"
    __table_args__ = {"schema": "land"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lender_name: Mapped[str] = mapped_column(String)
    principal_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    emi_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    emi_due_day: Mapped[int | None]
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoanInstallment(Base):
    __tablename__ = "loan_installments"
    __table_args__ = {"schema": "land"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    loan_obligation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("land.loan_obligations.id")
    )
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    instrument_type: Mapped[str] = mapped_column(String)
    reference_number: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
