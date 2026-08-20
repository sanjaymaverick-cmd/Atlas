"""Validated HTTP models for Phase 6 project controls."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atlas.modules.project_controls.schemas import (
    BimImportCreate,
    CostCodeCreate,
    IssuanceCreate,
    MaterialCreate,
    QuantityCreate,
    ReceiptCreate,
)


class DtoResponse(BaseModel):
    @classmethod
    def from_dto(cls, value: Any) -> Self:
        return cls(**{f: getattr(value, f) for f in cls.model_fields})


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: str = Field(min_length=1, max_length=50)


class ValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Decimal = Field(ge=0)


class BimImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_document_id: UUID

    def to_dto(self, project_id: UUID) -> BimImportCreate:
        return BimImportCreate(project_id, self.source_document_id)


class BimImportResponse(DtoResponse):
    id: UUID
    project_id: UUID
    source_document_id: UUID
    status: str
    validated_at: datetime | None
    validated_by: UUID | None
    version: int


class CostCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    parent_cost_code_id: UUID | None = None

    def to_dto(self, project_id: UUID) -> CostCodeCreate:
        return CostCodeCreate(project_id=project_id, **self.model_dump())


class CostCodeResponse(DtoResponse):
    id: UUID
    project_id: UUID
    code: str
    description: str | None
    wbs_level: int
    parent_cost_code_id: UUID | None
    version: int


class QuantityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calculated_quantity: Decimal = Field(ge=0)
    tolerance_pct: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    cost_code_id: UUID | None = None
    bim_object_id: UUID | None = None
    work_package: str | None = Field(default=None, max_length=200)

    def to_dto(self, project_id: UUID) -> QuantityCreate:
        return QuantityCreate(project_id=project_id, **self.model_dump())


class QuantityResponse(DtoResponse):
    id: UUID
    project_id: UUID
    calculated_quantity: Decimal | None
    verified_quantity: Decimal | None
    final_approved_quantity: Decimal | None
    tolerance_pct: Decimal
    status: str
    version: int


class MaterialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    unit_of_measure: str = Field(min_length=1, max_length=50)
    category: str | None = Field(default=None, max_length=100)

    def to_dto(self) -> MaterialCreate:
        return MaterialCreate(**self.model_dump())


class MaterialResponse(DtoResponse):
    id: UUID
    name: str
    unit_of_measure: str
    category: str | None
    version: int


class ReceiptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material_id: UUID
    quantity_received: Decimal = Field(gt=0)
    received_date: date
    purchase_order_id: UUID | None = None
    batch_reference: str | None = Field(default=None, max_length=200)
    certificate_document_id: UUID | None = None
    status: str = Field(default="received", pattern="^(received|partial)$")

    def to_dto(self, project_id: UUID) -> ReceiptCreate:
        return ReceiptCreate(project_id=project_id, **self.model_dump())


class ReceiptResponse(DtoResponse):
    id: UUID
    project_id: UUID
    material_id: UUID
    quantity_received: Decimal
    received_date: date
    status: str
    certificate_document_id: UUID | None
    version: int


class IssuanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_issued: Decimal = Field(gt=0)
    issued_date: date
    issued_to: str | None = Field(default=None, max_length=500)
    evidence_document_id: UUID | None = None

    def to_dto(self) -> IssuanceCreate:
        return IssuanceCreate(**self.model_dump())


class IssuanceResponse(DtoResponse):
    id: UUID
    project_id: UUID
    material_id: UUID
    material_receipt_id: UUID
    quantity_issued: Decimal
    issued_date: date
    evidence_document_id: UUID | None
    version: int
