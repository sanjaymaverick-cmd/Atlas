"""Thin HTTP adapters for Phase 4 commercial workflows."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.api.commercial_schemas import (
    BudgetCreateRequest,
    BudgetLineCreateRequest,
    BudgetLineResponse,
    BudgetResponse,
    ContractCreateRequest,
    ContractResponse,
    ContractTransitionRequest,
    InsuranceCreateRequest,
    InsuranceResponse,
    KycCreateRequest,
    KycDecisionRequest,
    KycResponse,
    LabourCreateRequest,
    LabourResponse,
    MilestoneCreateRequest,
    MilestoneResponse,
    OnboardingResponse,
    PurchaseOrderCreateRequest,
    PurchaseOrderLineCreateRequest,
    PurchaseOrderLineResponse,
    PurchaseOrderResponse,
    TransitionRequest,
)
from atlas.api.dependencies import ApiServices, get_current_session, get_services, get_session
from atlas.modules.identity.schemas import SessionContext

router = APIRouter(prefix="/api/v1", tags=["commercial"])
Actor = Annotated[SessionContext, Depends(get_current_session)]
Db = Annotated[AsyncSession, Depends(get_session)]
Services = Annotated[ApiServices, Depends(get_services)]


@router.get("/projects/{project_id}/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    project_id: UUID, actor: Actor, session: Db, services: Services
) -> list[BudgetResponse]:
    return [
        BudgetResponse.from_dto(v)
        for v in await services.commercial.list_budgets(
            session, actor_user_id=actor.user_id, project_id=project_id
        )
    ]


@router.post(
    "/projects/{project_id}/budgets",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget(
    project_id: UUID, body: BudgetCreateRequest, actor: Actor, session: Db, services: Services
) -> BudgetResponse:
    return BudgetResponse.from_dto(
        await services.commercial.create_budget(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post(
    "/budgets/{budget_id}/lines",
    response_model=BudgetLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_budget_line(
    budget_id: UUID, body: BudgetLineCreateRequest, actor: Actor, session: Db, services: Services
) -> BudgetLineResponse:
    return BudgetLineResponse.from_dto(
        await services.commercial.add_budget_line(
            session, actor_user_id=actor.user_id, budget_id=budget_id, data=body.to_dto()
        )
    )


@router.post("/budgets/{budget_id}/transition", response_model=BudgetResponse)
async def transition_budget(
    budget_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> BudgetResponse:
    return BudgetResponse.from_dto(
        await services.commercial.transition_budget(
            session,
            actor_user_id=actor.user_id,
            budget_id=budget_id,
            target_status=body.target_status,
        )
    )


@router.post(
    "/vendors/{vendor_id}/onboarding",
    response_model=OnboardingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_vendor(
    vendor_id: UUID, actor: Actor, session: Db, services: Services
) -> OnboardingResponse:
    return OnboardingResponse.from_dto(
        await services.commercial.invite_vendor(
            session, actor_user_id=actor.user_id, vendor_id=vendor_id
        )
    )


@router.post("/vendor-onboardings/{onboarding_id}/transition", response_model=OnboardingResponse)
async def transition_vendor(
    onboarding_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> OnboardingResponse:
    return OnboardingResponse.from_dto(
        await services.commercial.transition_vendor(
            session,
            actor_user_id=actor.user_id,
            onboarding_id=onboarding_id,
            target_status=body.target_status,
        )
    )


@router.post("/vendor-kyc-records", response_model=KycResponse, status_code=status.HTTP_201_CREATED)
async def add_kyc(
    body: KycCreateRequest, actor: Actor, session: Db, services: Services
) -> KycResponse:
    return KycResponse.from_dto(
        await services.commercial.add_kyc_record(
            session, actor_user_id=actor.user_id, data=body.to_dto()
        )
    )


@router.post("/vendor-kyc-records/{record_id}/decision", response_model=KycResponse)
async def decide_kyc(
    record_id: UUID, body: KycDecisionRequest, actor: Actor, session: Db, services: Services
) -> KycResponse:
    return KycResponse.from_dto(
        await services.commercial.verify_kyc_record(
            session, actor_user_id=actor.user_id, record_id=record_id, approve=body.approve
        )
    )


@router.post(
    "/projects/{project_id}/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_po(
    project_id: UUID,
    body: PurchaseOrderCreateRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> PurchaseOrderResponse:
    return PurchaseOrderResponse.from_dto(
        await services.commercial.create_purchase_order(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post(
    "/purchase-orders/{order_id}/lines",
    response_model=PurchaseOrderLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_po_line(
    order_id: UUID,
    body: PurchaseOrderLineCreateRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> PurchaseOrderLineResponse:
    return PurchaseOrderLineResponse.from_dto(
        await services.commercial.add_purchase_order_line(
            session, actor_user_id=actor.user_id, purchase_order_id=order_id, data=body.to_dto()
        )
    )


@router.post("/purchase-orders/{order_id}/transition", response_model=PurchaseOrderResponse)
async def transition_po(
    order_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> PurchaseOrderResponse:
    return PurchaseOrderResponse.from_dto(
        await services.commercial.transition_purchase_order(
            session,
            actor_user_id=actor.user_id,
            purchase_order_id=order_id,
            target_status=body.target_status,
        )
    )


@router.post(
    "/projects/{project_id}/contracts",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract(
    project_id: UUID, body: ContractCreateRequest, actor: Actor, session: Db, services: Services
) -> ContractResponse:
    return ContractResponse.from_dto(
        await services.commercial.create_contract(
            session, actor_user_id=actor.user_id, data=body.to_dto(project_id)
        )
    )


@router.post(
    "/contracts/{contract_id}/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_milestone(
    contract_id: UUID, body: MilestoneCreateRequest, actor: Actor, session: Db, services: Services
) -> MilestoneResponse:
    return MilestoneResponse.from_dto(
        await services.commercial.add_milestone(
            session, actor_user_id=actor.user_id, contract_id=contract_id, data=body.to_dto()
        )
    )


@router.post("/contracts/{contract_id}/transition", response_model=ContractResponse)
async def transition_contract(
    contract_id: UUID,
    body: ContractTransitionRequest,
    actor: Actor,
    session: Db,
    services: Services,
) -> ContractResponse:
    return ContractResponse.from_dto(
        await services.commercial.transition_contract(
            session,
            actor_user_id=actor.user_id,
            contract_id=contract_id,
            target_status=body.target_status,
            execution=body.execution(),
        )
    )


@router.post(
    "/vendor-insurance-policies",
    response_model=InsuranceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_insurance(
    body: InsuranceCreateRequest, actor: Actor, session: Db, services: Services
) -> InsuranceResponse:
    return InsuranceResponse.from_dto(
        await services.commercial.create_insurance(
            session, actor_user_id=actor.user_id, data=body.to_dto()
        )
    )


@router.post("/vendor-insurance-policies/{policy_id}/transition", response_model=InsuranceResponse)
async def transition_insurance(
    policy_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> InsuranceResponse:
    return InsuranceResponse.from_dto(
        await services.commercial.transition_insurance(
            session,
            actor_user_id=actor.user_id,
            policy_id=policy_id,
            target_status=body.target_status,
        )
    )


@router.post(
    "/labour-compliance-records", response_model=LabourResponse, status_code=status.HTTP_201_CREATED
)
async def create_labour(
    body: LabourCreateRequest, actor: Actor, session: Db, services: Services
) -> LabourResponse:
    return LabourResponse.from_dto(
        await services.commercial.create_labour_compliance(
            session, actor_user_id=actor.user_id, data=body.to_dto()
        )
    )


@router.post("/labour-compliance-records/{record_id}/transition", response_model=LabourResponse)
async def transition_labour(
    record_id: UUID, body: TransitionRequest, actor: Actor, session: Db, services: Services
) -> LabourResponse:
    return LabourResponse.from_dto(
        await services.commercial.transition_labour_compliance(
            session,
            actor_user_id=actor.user_id,
            record_id=record_id,
            target_status=body.target_status,
        )
    )
