from decimal import Decimal
from datetime import datetime, timezone
import pytest

from app.models.models import PaymentAttempt, PaymentIntent
from app.correlation.correlation_engine import CorrelationEngine
from app.domain.enums import CorrelationRelation

def test_hard_blocker_different_currencies():
    attempt_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("100"), currency="INR", state="INITIATED")
    attempt_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("100"), currency="USD", state="INITIATED")

    res = CorrelationEngine.evaluate(attempt_a, attempt_b)
    assert res.relation == CorrelationRelation.UNRELATED
    assert res.correlation_score == 0
    assert "currency_mismatch" in res.hard_blockers

def test_hard_blocker_different_order_ids():
    intent_a = PaymentIntent(order_id="ORD-1", customer_id="CUST-1", declared_amount=Decimal("100"))
    intent_b = PaymentIntent(order_id="ORD-2", customer_id="CUST-1", declared_amount=Decimal("100"))

    attempt_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("100"), currency="INR", state="INITIATED")
    attempt_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("100"), currency="INR", state="INITIATED")

    res = CorrelationEngine.evaluate(attempt_a, attempt_b, intent_a, intent_b)
    assert res.relation == CorrelationRelation.UNRELATED
    assert res.correlation_score == 0
    assert "distinct_order_ids" in res.hard_blockers

def test_sufficiency_gate_under_two_signals():
    # Only 1 signal (same amount), 0 other matching signals
    attempt_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("100"), currency="INR", state="INITIATED", created_at=datetime(2026,1,1,10,0,0, tzinfo=timezone.utc))
    attempt_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("100"), currency="INR", state="INITIATED", created_at=datetime(2026,1,1,12,0,0, tzinfo=timezone.utc))

    res = CorrelationEngine.evaluate(attempt_a, attempt_b)
    assert res.independent_signal_count == 1
    assert res.relation == CorrelationRelation.INSUFFICIENT_EVIDENCE

def test_related_multiple_signals():
    now = datetime.now(timezone.utc)
    intent_a = PaymentIntent(order_id="ORD-MATCH", customer_id="CUST-100", declared_amount=Decimal("2000"))
    intent_b = PaymentIntent(order_id="ORD-MATCH", customer_id="CUST-100", declared_amount=Decimal("2000"))

    attempt_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("2000"), currency="INR", state="INITIATED", created_at=now)
    attempt_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("2000"), currency="INR", state="INITIATED", created_at=now)

    res = CorrelationEngine.evaluate(attempt_a, attempt_b, intent_a, intent_b)
    assert res.correlation_score >= 80
    assert res.relation == CorrelationRelation.RELATED
    assert res.independent_signal_count >= 4
