from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.domain.enums import CorrelationRelation
from app.models.models import PaymentAttempt, PaymentIntent

class CorrelationSignalResult(BaseModel):
    signal: str
    matched: bool
    weight: int
    details: Optional[Dict[str, Any]] = None

class CorrelationEvaluationResult(BaseModel):
    relation: CorrelationRelation
    correlation_score: int
    signals: List[CorrelationSignalResult]
    hard_blockers: List[str]
    independent_signal_count: int


class CorrelationEngine:
    @staticmethod
    def evaluate(attempt_a: PaymentAttempt, attempt_b: PaymentAttempt, intent_a: Optional[PaymentIntent] = None, intent_b: Optional[PaymentIntent] = None) -> CorrelationEvaluationResult:
        signals: List[CorrelationSignalResult] = []
        hard_blockers: List[str] = []

        # 1. Hard Blockers Check
        if attempt_a.currency != attempt_b.currency:
            hard_blockers.append("currency_mismatch")

        order_id_a = intent_a.order_id if intent_a else None
        order_id_b = intent_b.order_id if intent_b else None
        if order_id_a and order_id_b and order_id_a != order_id_b:
            hard_blockers.append("distinct_order_ids")

        if hard_blockers:
            return CorrelationEvaluationResult(
                relation=CorrelationRelation.UNRELATED,
                correlation_score=0,
                signals=[],
                hard_blockers=hard_blockers,
                independent_signal_count=0
            )

        total_score = 0
        independent_matches = 0

        # Signal 1: Same Order ID (+40)
        matched_order = False
        if order_id_a and order_id_b and order_id_a == order_id_b:
            matched_order = True
            total_score += 40
            independent_matches += 1
        signals.append(CorrelationSignalResult(signal="same_order_id", matched=matched_order, weight=40))

        # Signal 2: Same Customer ID (+15)
        cust_a = intent_a.customer_id if intent_a else None
        cust_b = intent_b.customer_id if intent_b else None
        matched_cust = False
        if cust_a and cust_b and cust_a == cust_b:
            matched_cust = True
            total_score += 15
            independent_matches += 1
        signals.append(CorrelationSignalResult(signal="same_customer_id", matched=matched_cust, weight=15))

        # Signal 3 & 4: Exact Amount (+20) or Amount within 1% (+10)
        amt_a = attempt_a.amount
        amt_b = attempt_b.amount
        matched_exact_amt = False
        matched_near_amt = False

        if amt_a == amt_b:
            matched_exact_amt = True
            total_score += 20
            independent_matches += 1
        elif abs(amt_a - amt_b) <= (amt_a * Decimal("0.01")):
            matched_near_amt = True
            total_score += 10
            independent_matches += 1

        signals.append(CorrelationSignalResult(signal="exact_amount", matched=matched_exact_amt, weight=20))
        signals.append(CorrelationSignalResult(signal="amount_within_1_percent", matched=matched_near_amt, weight=10))

        # Signal 5 & 6: Time Difference (< 60s -> +15, 60-300s -> +8)
        time_diff = abs((attempt_a.created_at - attempt_b.created_at).total_seconds())
        matched_time_60 = False
        matched_time_300 = False

        if time_diff < 60:
            matched_time_60 = True
            total_score += 15
            independent_matches += 1
        elif time_diff <= 300:
            matched_time_300 = True
            total_score += 8
            independent_matches += 1

        signals.append(CorrelationSignalResult(signal="time_under_60s", matched=matched_time_60, weight=15, details={"seconds": time_diff}))
        signals.append(CorrelationSignalResult(signal="time_60_to_300s", matched=matched_time_300, weight=8, details={"seconds": time_diff}))

        # Signal 7: Previous Timeout (+10)
        has_timeout = attempt_a.state == "TIMED_OUT" or attempt_b.state == "TIMED_OUT"
        signals.append(CorrelationSignalResult(signal="previous_timeout", matched=has_timeout, weight=10))
        if has_timeout:
            total_score += 10
            independent_matches += 1

        # Signal 8: Retry Sequence Hint (+10)
        has_sequence_hint = (attempt_a.attempt_sequence_hint is not None and attempt_b.attempt_sequence_hint is not None and attempt_a.attempt_sequence_hint != attempt_b.attempt_sequence_hint)
        signals.append(CorrelationSignalResult(signal="retry_sequence_hint", matched=has_sequence_hint, weight=10))
        if has_sequence_hint:
            total_score += 10
            independent_matches += 1

        # Signal 9: Same Merchant Session (+10)
        matched_session = False
        if attempt_a.merchant_session_id and attempt_b.merchant_session_id and attempt_a.merchant_session_id == attempt_b.merchant_session_id:
            matched_session = True
            total_score += 10
            independent_matches += 1
        signals.append(CorrelationSignalResult(signal="same_merchant_session", matched=matched_session, weight=10))

        # Cap total score at 100
        score = min(100, total_score)

        # Sufficiency Gate: At least 2 independent signal matches required
        if independent_matches < 2:
            return CorrelationEvaluationResult(
                relation=CorrelationRelation.INSUFFICIENT_EVIDENCE,
                correlation_score=score,
                signals=signals,
                hard_blockers=[],
                independent_signal_count=independent_matches
            )

        # Determine relation from score thresholds
        if score >= 80:
            relation = CorrelationRelation.RELATED
        elif score >= 50:
            relation = CorrelationRelation.LIKELY_RELATED
        elif score >= 20:
            relation = CorrelationRelation.INSUFFICIENT_EVIDENCE
        else:
            relation = CorrelationRelation.UNRELATED

        return CorrelationEvaluationResult(
            relation=relation,
            correlation_score=score,
            signals=signals,
            hard_blockers=[],
            independent_signal_count=independent_matches
        )
