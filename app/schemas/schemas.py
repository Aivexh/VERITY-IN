from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.domain.enums import (
    AttemptState, IntentState, CorrelationRelation, ResolutionState,
    RootCauseType, ReviewDecision
)

class EventIngestionRequest(BaseModel):
    provider: str = Field(..., description="Provider name e.g. merchant, gateway_a, bank_a")
    provider_reference: str = Field(..., description="Unique provider transaction reference")
    event_type: str = Field(..., description="Event type e.g. INITIATED, BANK_SUCCESS, GATEWAY_CONFIRMED")
    amount: Decimal = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(default="INR", description="Currency code")
    order_id: Optional[str] = Field(None, description="Associated order identifier")
    customer_id: Optional[str] = Field(None, description="Associated customer identifier")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    merchant_session_id: Optional[str] = Field(None, description="Merchant session identifier")
    attempt_sequence_hint: Optional[int] = Field(None, description="Sequence hint for attempt retries")
    event_created_at: datetime = Field(..., description="Provider reported timestamp")
    raw_payload: Dict[str, Any] = Field(default_factory=dict, description="Raw event payload")

    model_config = ConfigDict(from_attributes=True)


class EventIngestionResponse(BaseModel):
    event_id: UUID
    attempt_id: UUID
    intent_id: Optional[UUID]
    dedup_hash: str
    is_duplicate: bool
    status: str
    processed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentEventResponse(BaseModel):
    id: UUID
    attempt_id: UUID
    event_type: str
    provider: str
    event_created_at: datetime
    event_received_at: datetime
    raw_payload: Dict[str, Any]
    dedup_hash: str

    model_config = ConfigDict(from_attributes=True)


class PaymentAttemptResponse(BaseModel):
    id: UUID
    intent_id: Optional[UUID]
    provider: str
    provider_reference: str
    amount: Decimal
    currency: str
    payment_method: Optional[str]
    merchant_session_id: Optional[str]
    attempt_sequence_hint: Optional[int]
    state: AttemptState
    created_at: datetime
    events: List[PaymentEventResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaymentIntentResponse(BaseModel):
    id: UUID
    order_id: str
    customer_id: str
    declared_amount: Decimal
    currency: str
    created_at: datetime
    aggregate_state: IntentState
    resolved_financial_transaction_id: Optional[UUID]
    attempts: List[PaymentAttemptResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CorrelationSignalResult(BaseModel):
    signal: str
    matched: bool
    weight: int
    details: Optional[Dict[str, Any]] = None


class CorrelationEvidenceResponse(BaseModel):
    relation: CorrelationRelation
    correlation_score: int
    signals: List[CorrelationSignalResult]
    hard_blockers: List[str]
    independent_signal_count: int


class FinancialResolutionResponse(BaseModel):
    id: UUID
    intent_id: UUID
    observed_amount: Decimal
    candidate_amount: Decimal
    committed_amount: Decimal
    resolution_state: ResolutionState
    selected_attempt_id: Optional[UUID]
    candidate_attempt_ids: List[UUID]
    resolution_confidence: Decimal
    reason: str
    evidence: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialTransactionResponse(BaseModel):
    id: UUID
    intent_id: UUID
    attempt_id: UUID
    amount: Decimal
    currency: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TimelineItem(BaseModel):
    event_id: UUID
    attempt_id: UUID
    provider: str
    event_type: str
    event_created_at: datetime
    event_received_at: datetime
    arrival_lag_seconds: float
    is_out_of_order: bool
    payload_summary: Dict[str, Any]


class TimelineResponse(BaseModel):
    intent_id: UUID
    total_events: int
    events: List[TimelineItem]


class IncidentAnalysisResponse(BaseModel):
    id: UUID
    intent_id: UUID
    primary_root_cause: RootCauseType
    root_cause_chain: List[Dict[str, Any]]
    correlation_evidence: Dict[str, Any]
    resolution: Dict[str, Any]
    naive_exposure: Dict[str, Any]
    recommendation: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentSummary(BaseModel):
    id: UUID
    intent_id: UUID
    order_id: str
    customer_id: str
    declared_amount: Decimal
    currency: str
    aggregate_state: IntentState
    primary_root_cause: Optional[str]
    observed_amount: Decimal
    candidate_amount: Decimal
    committed_amount: Decimal
    created_at: datetime


class IncidentDetailResponse(BaseModel):
    summary: IncidentSummary
    intent: PaymentIntentResponse
    resolution: Optional[FinancialResolutionResponse]
    analysis: Optional[IncidentAnalysisResponse]
    timeline: List[TimelineItem]


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    chosen_attempt_id: Optional[UUID] = Field(None, description="Required for CONFIRM_ATTEMPT")
    reviewer_note: str = Field(..., min_length=5, description="Auditable reviewer explanation")


class SimulationCreateRequest(BaseModel):
    scenario_id: str = Field(..., description="Scenario identifier e.g. NETWORK_TIMEOUT_RETRY")
    seed: int = Field(default=42, description="Seed for deterministic scenario generation")


class SimulationRunResponse(BaseModel):
    id: UUID
    scenario_id: str
    seed: int
    generated_event_hash: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    resolution_snapshot: Optional[Dict[str, Any]]
    engine_version: str

    model_config = ConfigDict(from_attributes=True)


class ExposureMetrics(BaseModel):
    total_observed_exposure: Decimal
    total_candidate_legitimate: Decimal
    total_committed_ledger: Decimal
    uncommitted_exposure_gap: Decimal
    naive_committable_exposure: Decimal


class DashboardSummaryResponse(BaseModel):
    total_intents: int
    total_attempts: int
    total_events: int
    total_incidents: int
    incidents_by_state: Dict[str, int]
    incidents_by_root_cause: Dict[str, int]
    exposure_metrics: ExposureMetrics
    latest_incidents: List[IncidentSummary]


class ExplanationResponse(BaseModel):
    intent_id: UUID
    ai_generated: bool
    explanation_text: str
    structured_evidence: Dict[str, Any]
