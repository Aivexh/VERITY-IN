from decimal import Decimal
from typing import Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.config.database import get_db
from app.schemas.schemas import DashboardSummaryResponse, ExposureMetrics, IncidentSummary
from app.models.models import PaymentIntent, PaymentAttempt, PaymentEvent, FinancialResolution, IncidentAnalysis
from app.repositories.repositories import PaymentIntentRepository, FinancialResolutionRepository, IncidentAnalysisRepository

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_intents = db.query(func.count(PaymentIntent.id)).scalar() or 0
    total_attempts = db.query(func.count(PaymentAttempt.id)).scalar() or 0
    total_events = db.query(func.count(PaymentEvent.id)).scalar() or 0

    # Incidents by state
    state_counts_raw = db.query(PaymentIntent.aggregate_state, func.count(PaymentIntent.id)).group_by(PaymentIntent.aggregate_state).all()
    incidents_by_state = {state.value: count for state, count in state_counts_raw}

    # Exposure metrics aggregation
    resolutions = db.query(FinancialResolution).all()

    total_observed = sum((r.observed_amount for r in resolutions), Decimal("0.00"))
    total_candidate = sum((r.candidate_amount for r in resolutions), Decimal("0.00"))
    total_committed = sum((r.committed_amount for r in resolutions), Decimal("0.00"))
    uncommitted_gap = total_observed - total_committed

    # Naive committable calculation across confirmed attempts
    confirmed_attempts = db.query(PaymentAttempt).filter(PaymentAttempt.state.in_(["CONFIRMED", "GATEWAY_CONFIRMED", "BANK_SUCCESS"])).all()
    naive_committable = sum((a.amount for a in confirmed_attempts), Decimal("0.00"))

    exposure = ExposureMetrics(
        total_observed_exposure=total_observed,
        total_candidate_legitimate=total_candidate,
        total_committed_ledger=total_committed,
        uncommitted_exposure_gap=uncommitted_gap,
        naive_committable_exposure=naive_committable
    )

    # Incidents by root cause
    analyses = db.query(IncidentAnalysis).all()
    incidents_by_cause: Dict[str, int] = {}
    for a in analyses:
        if a.root_cause_chain:
            cause = a.root_cause_chain[0].get("rule_id", "RC_UNKNOWN")
            incidents_by_cause[cause] = incidents_by_cause.get(cause, 0) + 1

    # Latest 10 incidents
    intent_repo = PaymentIntentRepository(db)
    res_repo = FinancialResolutionRepository(db)
    analysis_repo = IncidentAnalysisRepository(db)
    latest_intents = intent_repo.list_all(limit=10, offset=0)
    latest_summaries: List[IncidentSummary] = []

    for intent in latest_intents:
        res = res_repo.get_latest_for_intent(intent.id)
        an = analysis_repo.get_by_intent_id(intent.id)
        primary_cause = an.root_cause_chain[0].get("rule_id") if (an and an.root_cause_chain) else None

        latest_summaries.append(IncidentSummary(
            id=an.id if an else intent.id,
            intent_id=intent.id,
            order_id=intent.order_id,
            customer_id=intent.customer_id,
            declared_amount=intent.declared_amount,
            currency=intent.currency,
            aggregate_state=intent.aggregate_state,
            primary_root_cause=primary_cause,
            observed_amount=res.observed_amount if res else intent.declared_amount,
            candidate_amount=res.candidate_amount if res else intent.declared_amount,
            committed_amount=res.committed_amount if res else 0,
            created_at=intent.created_at
        ))

    return DashboardSummaryResponse(
        total_intents=total_intents,
        total_attempts=total_attempts,
        total_events=total_events,
        total_incidents=total_intents,
        incidents_by_state=incidents_by_state,
        incidents_by_root_cause=incidents_by_cause,
        exposure_metrics=exposure,
        latest_incidents=latest_summaries
    )
