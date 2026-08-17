"""ORM mappings onto canonical Phase 6 schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Numeric, String
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


class BimImport(AuditColumns, Base):
    __tablename__ = "bim_imports"
    __table_args__ = {"schema": "design"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_file_reference: Mapped[str]
    source_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    import_status: Mapped[str]
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class BimObject(Base):
    __tablename__ = "bim_objects"
    __table_args__ = {"schema": "design"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    bim_import_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class CostCode(AuditColumns, Base):
    __tablename__ = "cost_codes"
    __table_args__ = {"schema": "quantities"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    code: Mapped[str]
    description: Mapped[str | None]
    wbs_level: Mapped[int]
    parent_cost_code_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class QuantityItem(AuditColumns, Base):
    __tablename__ = "quantity_items"
    __table_args__ = {"schema": "quantities"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    cost_code_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    bim_object_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    work_package: Mapped[str | None]
    calculated_quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    verified_quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    proposed_resolution: Mapped[str | None]
    final_approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    status: Mapped[str]


class Material(AuditColumns, Base):
    __tablename__ = "materials"
    __table_args__ = {"schema": "inventory"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    name: Mapped[str]
    unit_of_measure: Mapped[str]
    category: Mapped[str | None]


class MaterialReceipt(AuditColumns, Base):
    __tablename__ = "material_receipts"
    __table_args__ = {"schema": "inventory"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    purchase_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    batch_reference: Mapped[str | None]
    certificate_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    received_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str]


class MaterialIssuance(AuditColumns, Base):
    __tablename__ = "material_issuances"
    __table_args__ = {"schema": "inventory"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    material_receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    quantity_issued: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    issued_to: Mapped[str | None] = mapped_column(String)
    issued_date: Mapped[date] = mapped_column(Date)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
