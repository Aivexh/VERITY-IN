import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel

from app.domain.enums import ResolutionState, IntentState, AttemptState, RootCauseType
from app.models.models import PaymentIntent, PaymentAttempt, PaymentEvent, TransactionLink
from app.rules.root_cause_engine import RootCauseRuleResult

class TruthEngineResolutionResult(BaseModel):
    observed_amount: Decimal
    candidate_amount: Decimal
    committed_amount: Decimal
    resolution_state: ResolutionState
    intent_state: IntentState
    selected_attempt_id: Optional[UUID]
    candidate_attempt_ids: List[UUID]
    resolution_confidence: Decimal
    reason: str
    evidence: Dict[str, Any]


class TruthEngine:
    @staticmethod
    def resolve(
        intent: PaymentIntent,
        attempts: List[PaymentAttempt],
        events: List[PaymentEvent],
        links: List[TransactionLink],
        causal_chain: List[RootCauseRuleResult],
        is_exact_duplicate_event: bool = False
    ) -> TruthEngineResolutionResult:
        # Calculate Observed Exposure (Sum of all attempts created)
        observed_amount = sum((a.amount for a in attempts), Decimal("0.00"))
        candidate_amount = intent.declared_amount
        committed_amount = Decimal("0.00")  # Never auto-committed here!

        # Ensure attempt IDs are non-none UUIDs even in unit tests before DB flush
        for a in attempts:
            if getattr(a, "id", None) is None:
                a.id = uuid.uuid4()

        candidate_attempt_ids = [a.id for a in attempts]
        primary_cause = causal_chain[0].rule_id if causal_chain else RootCauseType.RC_UNKNOWN

        # Check existing financial transaction
        if intent.resolved_financial_transaction_id is not None:
            # Already committed by explicit ledger path
            committed_amount = intent.declared_amount
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=committed_amount,
                resolution_state=ResolutionState.COMMITTED,
                intent_state=IntentState.CONFIRMED,
                selected_attempt_id=None,
                candidate_attempt_ids=candidate_attempt_ids,
                resolution_confidence=Decimal("1.0000"),
                reason="Financial transaction successfully committed to ledger.",
                evidence={"committed_tx_id": str(intent.resolved_financial_transaction_id)}
            )

        # Count confirmed attempts
        confirmed_attempts = [
            a for a in attempts
            if a.state in (AttemptState.CONFIRMED, AttemptState.GATEWAY_CONFIRMED, AttemptState.BANK_SUCCESS)
        ]

        failed_attempts = [
            a for a in attempts
            if a.state in (AttemptState.FAILED, AttemptState.GATEWAY_FAILED, AttemptState.BANK_FAILED)
        ]

        # Calculate Resolution Confidence deterministically
        confidence = Decimal("1.0000")
        for rule in causal_chain:
            confidence = confidence * Decimal(str(rule.confidence_impact))

        # Scenario 1: Provider Contradiction (e.g. BANK_SUCCESS + GATEWAY_FAILED)
        if primary_cause == RootCauseType.RC_CONFLICTING_PROVIDER:
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=Decimal("0.00"),
                resolution_state=ResolutionState.CONFLICTING_STATE,
                intent_state=IntentState.CONFLICTING_STATE,
                selected_attempt_id=None,
                candidate_attempt_ids=candidate_attempt_ids,
                resolution_confidence=Decimal("0.5000"),
                reason="Provider observations are contradictory for attempt.",
                evidence={"cause": primary_cause.value, "failed_count": len(failed_attempts)}
            )

        # Scenario 2: Multiple Confirmed / Related Attempts (e.g. Canonical Timeout + Retry)
        if len(confirmed_attempts) > 1 or (len(attempts) > 1 and len(confirmed_attempts) >= 1 and primary_cause in (RootCauseType.RC_NETWORK_TIMEOUT, RootCauseType.RC_CUSTOMER_RETRY)):
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=Decimal("0.00"),
                resolution_state=ResolutionState.HELD_FOR_REVIEW,
                intent_state=IntentState.POTENTIAL_DUPLICATE,
                selected_attempt_id=None,
                candidate_attempt_ids=[a.id for a in confirmed_attempts] if confirmed_attempts else candidate_attempt_ids,
                resolution_confidence=confidence,
                reason=f"Multiple confirmed or retry payment attempts ({len(confirmed_attempts)}) detected. Held for manual review to prevent duplicate charging.",
                evidence={
                    "observed_exposure": float(observed_amount),
                    "candidate_amount": float(candidate_amount),
                    "primary_root_cause": primary_cause.value,
                    "confirmed_attempt_ids": [str(a.id) for a in confirmed_attempts]
                }
            )

        # Scenario 3: Single Confirmed Attempt (Normal Case)
        if len(confirmed_attempts) == 1 and len(attempts) == 1:
            selected_attempt = confirmed_attempts[0]
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=Decimal("0.00"),  # Eligible for commit, but committed_amount remains 0 until ledger service writes
                resolution_state=ResolutionState.SAFE_TO_COMMIT,
                intent_state=IntentState.CONFIRMED,
                selected_attempt_id=selected_attempt.id,
                candidate_attempt_ids=[selected_attempt.id],
                resolution_confidence=Decimal("0.9900"),
                reason="Single legitimate attempt confirmed. Safe for financial ledger commitment.",
                evidence={"selected_attempt_id": str(selected_attempt.id), "provider_ref": selected_attempt.provider_reference}
            )

        # Scenario 4: Missing evidence or pending events
        if not confirmed_attempts and not failed_attempts:
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=Decimal("0.00"),
                resolution_state=ResolutionState.INSUFFICIENT_EVIDENCE,
                intent_state=IntentState.INSUFFICIENT_EVIDENCE,
                selected_attempt_id=None,
                candidate_attempt_ids=candidate_attempt_ids,
                resolution_confidence=Decimal("0.4000"),
                reason="Insufficient evidence received to determine payment outcome.",
                evidence={"attempts_count": len(attempts)}
            )

        # Scenario 5: All failed attempts
        if len(failed_attempts) == len(attempts) and len(attempts) > 0:
            return TruthEngineResolutionResult(
                observed_amount=observed_amount,
                candidate_amount=candidate_amount,
                committed_amount=Decimal("0.00"),
                resolution_state=ResolutionState.REJECTED,
                intent_state=IntentState.FAILED,
                selected_attempt_id=None,
                candidate_attempt_ids=candidate_attempt_ids,
                resolution_confidence=Decimal("0.9500"),
                reason="All payment attempts failed.",
                evidence={"failed_count": len(failed_attempts)}
            )

        # Fallback Ambiguity -> MANUAL_REVIEW
        return TruthEngineResolutionResult(
            observed_amount=observed_amount,
            candidate_amount=candidate_amount,
            committed_amount=Decimal("0.00"),
            resolution_state=ResolutionState.MANUAL_REVIEW,
            intent_state=IntentState.MANUAL_REVIEW,
            selected_attempt_id=None,
            candidate_attempt_ids=candidate_attempt_ids,
            resolution_confidence=confidence,
            reason="Ambiguous payment history requires explicit manual reviewer decision.",
            evidence={"attempts_count": len(attempts)}
        )
