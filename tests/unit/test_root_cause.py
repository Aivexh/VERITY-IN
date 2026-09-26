from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.models.models import PaymentIntent, PaymentAttempt, PaymentEvent
from app.rules.root_cause_engine import RootCauseEngine
from app.domain.enums import RootCauseType

def test_root_cause_duplicate_webhook():
    intent = PaymentIntent(order_id="O1", customer_id="C1", declared_amount=Decimal("100"))
    attempts = [PaymentAttempt(provider="gw", provider_reference="r1", amount=Decimal("100"))]
    events = [PaymentEvent(attempt_id=attempts[0].id, event_type="INITIATED", provider="gw", event_created_at=datetime.now(timezone.utc), dedup_hash="abc")]

    causal = RootCauseEngine.evaluate(intent, attempts, events, has_duplicate_hash=True)
    rule_ids = [c.rule_id for c in causal]
    assert RootCauseType.RC_DUPLICATE_WEBHOOK in rule_ids

def test_root_cause_network_timeout():
    now = datetime.now(timezone.utc)
    intent = PaymentIntent(order_id="O1", customer_id="C1", declared_amount=Decimal("2000"))
    att_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("2000"))
    att_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("2000"))

    events = [
        PaymentEvent(attempt_id=att_a.id, event_type="BANK_SUCCESS", provider="bank", event_created_at=now, dedup_hash="h1"),
        PaymentEvent(attempt_id=att_a.id, event_type="TIMED_OUT", provider="gw_a", event_created_at=now + timedelta(seconds=10), dedup_hash="h2")
    ]

    causal = RootCauseEngine.evaluate(intent, [att_a, att_b], events)
    rule_ids = [c.rule_id for c in causal]
    assert RootCauseType.RC_NETWORK_TIMEOUT in rule_ids
    assert RootCauseEngine.select_primary_cause(causal) == RootCauseType.RC_NETWORK_TIMEOUT

def test_root_cause_conflicting_provider():
    now = datetime.now(timezone.utc)
    intent = PaymentIntent(order_id="O1", customer_id="C1", declared_amount=Decimal("2000"))
    att_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("2000"))

    events = [
        PaymentEvent(attempt_id=att_a.id, event_type="BANK_SUCCESS", provider="bank", event_created_at=now, dedup_hash="h1"),
        PaymentEvent(attempt_id=att_a.id, event_type="GATEWAY_FAILED", provider="gw_a", event_created_at=now + timedelta(seconds=5), dedup_hash="h2")
    ]

    causal = RootCauseEngine.evaluate(intent, [att_a], events)
    rule_ids = [c.rule_id for c in causal]
    assert RootCauseType.RC_CONFLICTING_PROVIDER in rule_ids
    assert RootCauseEngine.select_primary_cause(causal) == RootCauseType.RC_CONFLICTING_PROVIDER
