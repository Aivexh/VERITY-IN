from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.schemas.schemas import (
    FinancialTransactionResponse, TimelineResponse, IncidentAnalysisResponse, ExplanationResponse
)
from app.repositories.repositories import (
    FinancialTransactionRepository, PaymentIntentRepository, PaymentEventRepository, IncidentAnalysisRepository
)
from app.services.timeline_service import TimelineService
from app.services.explanation_service import ExplanationService

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

@router.get("", response_model=List[FinancialTransactionResponse])
def list_transactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    repo = FinancialTransactionRepository(db)
    return repo.list_all(limit=limit, offset=offset)

@router.get("/{id}", response_model=FinancialTransactionResponse)
def get_transaction(id: UUID, db: Session = Depends(get_db)):
    repo = FinancialTransactionRepository(db)
    tx = repo.get_by_intent_id(id)
    if not tx:
        # Also check by transaction ID
        tx = repo.db.query(repo.get_by_intent_id.__self__.model).filter_by(id=id).first()
    if not tx:
        raise HTTPException(status_code=444, detail=f"Financial transaction {id} not found")
    return tx

@router.get("/{id}/timeline", response_model=TimelineResponse)
def get_transaction_timeline(id: UUID, db: Session = Depends(get_db)):
    event_repo = PaymentEventRepository(db)
    intent_repo = PaymentIntentRepository(db)

    intent = intent_repo.get_by_id(id)
    if not intent:
        raise HTTPException(status_code=444, detail=f"Payment intent {id} not found")

    events = event_repo.get_events_for_intent(id)
    return TimelineService.build_timeline(id, events)

@router.get("/{id}/analysis", response_model=IncidentAnalysisResponse)
def get_transaction_analysis(id: UUID, db: Session = Depends(get_db)):
    repo = IncidentAnalysisRepository(db)
    analysis = repo.get_by_intent_id(id)
    if not analysis:
        raise HTTPException(status_code=444, detail=f"Incident analysis for intent {id} not found")

    primary_cause = analysis.root_cause_chain[0].get("rule_id", "RC_UNKNOWN") if analysis.root_cause_chain else "RC_UNKNOWN"
    res_dict = analysis.resolution or {}
    cand_amt = float(res_dict.get("candidate_amount", 0))
    comm_amt = float(res_dict.get("committed_amount", 0))
    obs_amt = float(res_dict.get("observed_amount", 0))

    naive_exposure = {
        "naive_observed_amount": obs_amt,
        "verity_candidate_amount": cand_amt,
        "verity_committed_amount": comm_amt,
        "naive_overestimation": max(0.0, obs_amt - cand_amt)
    }

    return IncidentAnalysisResponse(
        id=analysis.id,
        intent_id=analysis.intent_id,
        primary_root_cause=primary_cause,
        root_cause_chain=analysis.root_cause_chain,
        correlation_evidence=analysis.correlation_evidence,
        resolution=analysis.resolution,
        naive_exposure=naive_exposure,
        recommendation=analysis.recommendation,
        created_at=analysis.created_at
    )

@router.post("/{id}/explain", response_model=ExplanationResponse)
def explain_transaction(id: UUID, db: Session = Depends(get_db)):
    repo = IncidentAnalysisRepository(db)
    analysis = repo.get_by_intent_id(id)
    if not analysis:
        raise HTTPException(status_code=444, detail=f"Incident analysis for intent {id} not found")

    return ExplanationService.generate_explanation(id, analysis)
