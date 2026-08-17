"""ORM mappings onto canonical Phase 4 commercial schemas."""

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


class Budget(AuditColumns, Base):
    __tablename__ = "budgets"
    __table_args__ = {"schema": "budget"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    legal_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[str] = mapped_column(String)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BudgetLine(AuditColumns, Base):
    __tablename__ = "budget_lines"
    __table_args__ = {"schema": "budget"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    budget_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    cost_code_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(String)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    committed_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[str] = mapped_column(String)


class PurchaseOrder(AuditColumns, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"schema": "procurement"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    budget_line_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[str] = mapped_column(String)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrderLine(AuditColumns, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = {"schema": "procurement"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    purchase_order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    cost_code_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(String)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))


class Contract(AuditColumns, Base):
    __tablename__ = "contracts"
    __table_args__ = {"schema": "contracts"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    party_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    contract_type: Mapped[str | None] = mapped_column(String)
    value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    status: Mapped[str] = mapped_column(String)
    execution_method: Mapped[str | None] = mapped_column(String)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class ContractMilestone(AuditColumns, Base):
    __tablename__ = "contract_milestones"
    __table_args__ = {"schema": "contracts"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    description: Mapped[str | None] = mapped_column(String)
    due_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String)


class VendorOnboarding(AuditColumns, Base):
    __tablename__ = "vendor_onboardings"
    __table_args__ = {"schema": "vendor_onboarding"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    vendor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kyc_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bank_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    compliance_docs_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class KycRecord(AuditColumns, Base):
    __tablename__ = "kyc_records"
    __table_args__ = {"schema": "vendor_onboarding"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    party_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    document_type: Mapped[str] = mapped_column(String)
    document_reference: Mapped[str | None] = mapped_column(String)
    object_storage_key: Mapped[str | None] = mapped_column(String)
    evidence_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    verification_status: Mapped[str] = mapped_column(String)
    verified_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InsurancePolicy(AuditColumns, Base):
    __tablename__ = "insurance_policies"
    __table_args__ = {"schema": "vendor_onboarding"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    contract_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    vendor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    policy_number: Mapped[str] = mapped_column(String)
    insurer: Mapped[str | None] = mapped_column(String)
    coverage_type: Mapped[str] = mapped_column(String)
    sum_insured: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String)


class LabourComplianceRecord(AuditColumns, Base):
    __tablename__ = "labour_compliance_records"
    __table_args__ = {"schema": "vendor_onboarding"}
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    contractor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    pf_registration_number: Mapped[str | None] = mapped_column(String)
    esi_registration_number: Mapped[str | None] = mapped_column(String)
    contract_labour_licence_number: Mapped[str | None] = mapped_column(String)
    minimum_wage_evidence_ref: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
