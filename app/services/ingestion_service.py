import hashlib
import json
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.schemas.schemas import EventIngestionRequest, EventIngestionResponse
from app.models.models import (
    PaymentIntent, PaymentAttempt, PaymentEvent, TransactionLink,
    FinancialResolution, IncidentAnalysis
)
from app.domain.enums import AttemptState, IntentState
from app.repositories.repositories import (
    PaymentIntentRepository, PaymentAttemptRepository, PaymentEventRepository,
    TransactionLinkRepository, FinancialResolutionRepository, IncidentAnalysisRepository
)
from app.state_machine.state_machine import StateMachine
from app.correlation.correlation_engine import CorrelationEngine
from app.rules.root_cause_engine import RootCauseEngine
from app.truth_engine.truth_engine import TruthEngine
from app.services.audit_service import AuditService
from app.services.naive_engine import NaiveEngine

class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.intent_repo = PaymentIntentRepository(db)
        self.attempt_repo = PaymentAttemptRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.link_repo = TransactionLinkRepository(db)
        self.resolution_repo = FinancialResolutionRepository(db)
        self.analysis_repo = IncidentAnalysisRepository(db)
        self.audit_service = AuditService(db)

    @staticmethod
    def compute_dedup_hash(req: EventIngestionRequest) -> str:
        payload_str = json.dumps(req.raw_payload, sort_keys=True)
        raw_str = f"{req.provider}:{req.provider_reference}:{req.event_type}:{req.amount}:{req.currency}:{req.event_created_at.isoformat()}:{payload_str}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def ingest_event(self, req: EventIngestionRequest) -> EventIngestionResponse:
        dedup_hash = self.compute_dedup_hash(req)

        # 1. Deduplication check (Invariant I1 & I5)
        existing_event = self.event_repo.get_by_dedup_hash(dedup_hash)
        if existing_event:
            self.audit_service.log_event(
                entity_type="PaymentEvent",
                entity_id=existing_event.id,
                action="DUPLICATE_EVENT_RECEIVED",
                details={"dedup_hash": dedup_hash, "provider_ref": req.provider_reference}
            )
            return EventIngestionResponse(
                event_id=existing_event.id,
                attempt_id=existing_event.attempt_id,
                intent_id=existing_event.attempt.intent_id if existing_event.attempt else None,
                dedup_hash=dedup_hash,
                is_duplicate=True,
                status="IDEMPOTENT_NOOP",
                processed_at=datetime.now(timezone.utc)
            )

        # 2. Get or Create PaymentIntent
        intent: Optional[PaymentIntent] = None
        if req.order_id:
            intent = self.intent_repo.get_by_order_id(req.order_id)

        if not intent:
            intent = PaymentIntent(
                order_id=req.order_id or f"ORD-{req.provider_reference}",
                customer_id=req.customer_id or "CUST-DEFAULT",
                declared_amount=req.amount,
                currency=req.currency,
                aggregate_state=IntentState.PENDING
            )
            intent = self.intent_repo.create(intent)

        # 3. Get or Create PaymentAttempt
        attempt = self.attempt_repo.get_by_provider_reference(req.provider, req.provider_reference)
        if not attempt:
            mapped_state = AttemptState.INITIATED
            if req.event_type in ("BANK_SUCCESS", "GATEWAY_CONFIRMED", "CONFIRMED"):
                mapped_state = AttemptState.CONFIRMED
            elif req.event_type in ("BANK_FAILED", "GATEWAY_FAILED", "FAILED"):
                mapped_state = AttemptState.FAILED

            attempt = PaymentAttempt(
                intent_id=intent.id,
                provider=req.provider,
                provider_reference=req.provider_reference,
                amount=req.amount,
                currency=req.currency,
                payment_method=req.payment_method,
                merchant_session_id=req.merchant_session_id,
                attempt_sequence_hint=req.attempt_sequence_hint,
                state=mapped_state
            )
            attempt = self.attempt_repo.create(attempt)
        else:
            next_state = attempt.state
            if req.event_type in ("BANK_SUCCESS", "GATEWAY_CONFIRMED", "CONFIRMED"):
                next_state = AttemptState.CONFIRMED
            elif req.event_type in ("BANK_FAILED", "GATEWAY_FAILED", "FAILED"):
                next_state = AttemptState.FAILED
            elif req.event_type in ("TIMED_OUT", "TIMEOUT_DETECTED"):
                next_state = AttemptState.TIMED_OUT

            StateMachine.validate_attempt_transition(attempt.state, next_state)
            attempt.state = next_state

        # 4. Persist Immutable PaymentEvent
        event = PaymentEvent(
            attempt_id=attempt.id,
            event_type=req.event_type,
            provider=req.provider,
            event_created_at=req.event_created_at,
            event_received_at=datetime.now(timezone.utc),
            raw_payload=req.raw_payload or {"provider_ref": req.provider_reference, "type": req.event_type},
            dedup_hash=dedup_hash
        )
        event = self.event_repo.create(event)

        # 5. Correlation & Linking with sibling attempts
        all_attempts_for_intent = self.attempt_repo.get_attempts_for_intent(intent.id)
        links: list[TransactionLink] = []

        for other_attempt in all_attempts_for_intent:
            if other_attempt.id != attempt.id:
                corr_res = CorrelationEngine.evaluate(attempt, other_attempt, intent, intent)
                link = TransactionLink(
                    source_attempt_id=attempt.id,
                    target_attempt_id=other_attempt.id,
                    relation=corr_res.relation,
                    correlation_score=corr_res.correlation_score,
                    correlation_evidence=corr_res.model_dump(mode="json")
                )
                self.link_repo.create(link)
                links.append(link)

        # 6. Rebuild timeline and Root Cause Analysis
        all_events_for_intent = self.event_repo.get_events_for_intent(intent.id)
        causal_chain = RootCauseEngine.evaluate(intent, all_attempts_for_intent, all_events_for_intent)

        # 7. Financial Truth Engine Resolution
        resolution_result = TruthEngine.resolve(
            intent=intent,
            attempts=all_attempts_for_intent,
            events=all_events_for_intent,
            links=links,
            causal_chain=causal_chain
        )

        # Save FinancialResolution
        fin_res = FinancialResolution(
            intent_id=intent.id,
            observed_amount=resolution_result.observed_amount,
            candidate_amount=resolution_result.candidate_amount,
            committed_amount=resolution_result.committed_amount,
            resolution_state=resolution_result.resolution_state,
            selected_attempt_id=resolution_result.selected_attempt_id,
            candidate_attempt_ids=[str(i) for i in resolution_result.candidate_attempt_ids],
            resolution_confidence=resolution_result.resolution_confidence,
            reason=resolution_result.reason,
            evidence=resolution_result.evidence
        )
        self.resolution_repo.create(fin_res)

        # Update Intent State via State Machine
        StateMachine.validate_intent_transition(intent.aggregate_state, resolution_result.intent_state)
        intent.aggregate_state = resolution_result.intent_state

        # Calculate Naive Comparison
        naive_data = NaiveEngine.calculate_naive_exposure(
            attempts=all_attempts_for_intent,
            verity_candidate_amount=resolution_result.candidate_amount,
            verity_committed_amount=resolution_result.committed_amount
        )

        # Save Incident Analysis using mode="json" for pydantic serialization
        incident_analysis = IncidentAnalysis(
            intent_id=intent.id,
            root_cause_chain=[c.model_dump(mode="json") for c in causal_chain],
            correlation_evidence={
                "links_count": len(links),
                "relations": [l.relation.value for l in links]
            },
            resolution=resolution_result.model_dump(mode="json"),
            recommendation=causal_chain[0].recommended_action if causal_chain else "AUTO_PROCESS"
        )
        self.analysis_repo.create(incident_analysis)

        # Write Audit Log
        self.audit_service.log_event(
            entity_type="PaymentEvent",
            entity_id=event.id,
            action="INGEST_EVENT",
            details={
                "intent_id": str(intent.id),
                "attempt_id": str(attempt.id),
                "event_type": req.event_type,
                "intent_state": intent.aggregate_state.value,
                "resolution_state": resolution_result.resolution_state.value
            }
        )

        self.db.commit()

        return EventIngestionResponse(
            event_id=event.id,
            attempt_id=attempt.id,
            intent_id=intent.id,
            dedup_hash=dedup_hash,
            is_duplicate=False,
            status="PROCESSED",
            processed_at=datetime.now(timezone.utc)
        )
