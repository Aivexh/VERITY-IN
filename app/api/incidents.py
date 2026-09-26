from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.schemas.schemas import (
    IncidentSummary, IncidentDetailResponse, ReviewRequest, FinancialResolutionResponse,
    IncidentAnalysisResponse, PaymentIntentResponse
)
from app.repositories.repositories import (
    PaymentIntentRepository, FinancialResolutionRepository, IncidentAnalysisRepository, PaymentEventRepository
)
from app.services.review_service import ReviewService
from app.services.timeline_service import TimelineService
from app.domain.enums import IntentState

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])

@router.get("", response_model=List[IncidentSummary])
def list_incidents(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    intent_repo = PaymentIntentRepository(db)
    res_repo = FinancialResolutionRepository(db)
    analysis_repo = IncidentAnalysisRepository(db)

    intents = intent_repo.list_all(limit=limit, offset=offset)
    summaries: List[IncidentSummary] = []

    for intent in intents:
        resolution = res_repo.get_latest_for_intent(intent.id)
        analysis = analysis_repo.get_by_intent_id(intent.id)

        primary_cause = None
        if analysis and analysis.root_cause_chain:
            primary_cause = analysis.root_cause_chain[0].get("rule_id")

        obs = resolution.observed_amount if resolution else intent.declared_amount
        cand = resolution.candidate_amount if resolution else intent.declared_amount
        comm = resolution.committed_amount if resolution else 0

        summaries.append(IncidentSummary(
            id=analysis.id if analysis else intent.id,
            intent_id=intent.id,
            order_id=intent.order_id,
            customer_id=intent.customer_id,
            declared_amount=intent.declared_amount,
            currency=intent.currency,
            aggregate_state=intent.aggregate_state,
            primary_root_cause=primary_cause,
            observed_amount=obs,
            candidate_amount=cand,
            committed_amount=comm,
            created_at=intent.created_at
        ))

    return summaries

@router.get("/{id}", response_model=IncidentDetailResponse)
def get_incident(id: UUID, db: Session = Depends(get_db)):
    intent_repo = PaymentIntentRepository(db)
    res_repo = FinancialResolutionRepository(db)
    analysis_repo = IncidentAnalysisRepository(db)
    event_repo = PaymentEventRepository(db)

    intent = intent_repo.get_by_id(id)
    if not intent:
        # Check if ID is analysis ID
        analysis_by_id = db.query(analysis_repo.get_by_intent_id.__self__.model).filter_by(id=id).first()
        if analysis_by_id:
            intent = intent_repo.get_by_id(analysis_by_id.intent_id)

    if not intent:
        raise HTTPException(status_code=444, detail=f"Incident {id} not found")

    resolution = res_repo.get_latest_for_intent(intent.id)
    analysis = analysis_repo.get_by_intent_id(intent.id)
    events = event_repo.get_events_for_intent(intent.id)
    timeline = TimelineService.build_timeline(intent.id, events)

    primary_cause = None
    if analysis and analysis.root_cause_chain:
        primary_cause = analysis.root_cause_chain[0].get("rule_id")

    obs = resolution.observed_amount if resolution else intent.declared_amount
    cand = resolution.candidate_amount if resolution else intent.declared_amount
    comm = resolution.committed_amount if resolution else 0

    summary = IncidentSummary(
        id=analysis.id if analysis else intent.id,
        intent_id=intent.id,
        order_id=intent.order_id,
        customer_id=intent.customer_id,
        declared_amount=intent.declared_amount,
        currency=intent.currency,
        aggregate_state=intent.aggregate_state,
        primary_root_cause=primary_cause,
        observed_amount=obs,
        candidate_amount=cand,
        committed_amount=comm,
        created_at=intent.created_at
    )

    analysis_resp = None
    if analysis:
        res_dict = analysis.resolution or {}
        cand_amt = float(res_dict.get("candidate_amount", 0))
        comm_amt = float(res_dict.get("committed_amount", 0))
        obs_amt = float(res_dict.get("observed_amount", 0))
        naive_exp = {
            "naive_observed_amount": obs_amt,
            "verity_candidate_amount": cand_amt,
            "verity_committed_amount": comm_amt,
            "naive_overestimation": max(0.0, obs_amt - cand_amt)
        }
        analysis_resp = IncidentAnalysisResponse(
            id=analysis.id,
            intent_id=analysis.intent_id,
            primary_root_cause=primary_cause or "RC_UNKNOWN",
            root_cause_chain=analysis.root_cause_chain,
            correlation_evidence=analysis.correlation_evidence,
            resolution=analysis.resolution,
            naive_exposure=naive_exp,
            recommendation=analysis.recommendation,
            created_at=analysis.created_at
        )

    res_resp = None
    if resolution:
        res_resp = FinancialResolutionResponse(
            id=resolution.id,
            intent_id=resolution.intent_id,
            observed_amount=resolution.observed_amount,
            candidate_amount=resolution.candidate_amount,
            committed_amount=resolution.committed_amount,
            resolution_state=resolution.resolution_state,
            selected_attempt_id=resolution.selected_attempt_id,
            candidate_attempt_ids=[UUID(i) if isinstance(i, str) else i for i in resolution.candidate_attempt_ids],
            resolution_confidence=resolution.resolution_confidence,
            reason=resolution.reason,
            evidence=resolution.evidence,
            created_at=resolution.created_at
        )

    return IncidentDetailResponse(
        summary=summary,
        intent=PaymentIntentResponse.model_validate(intent),
        resolution=res_resp,
        analysis=analysis_resp,
        timeline=timeline.events
    )

@router.post("/{id}/review")
def review_incident(id: UUID, req: ReviewRequest, db: Session = Depends(get_db)):
    service = ReviewService(db)
    return service.process_review(intent_id=id, request=req)
