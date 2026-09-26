from decimal import Decimal
from datetime import datetime, timezone
import pytest

from app.models.models import PaymentIntent, PaymentAttempt, PaymentEvent
from app.truth_engine.truth_engine import TruthEngine
from app.domain.enums import ResolutionState, IntentState, AttemptState, RootCauseType
from app.rules.root_cause_engine import RootCauseRuleResult

def test_truth_engine_normal_single_success():
    intent = PaymentIntent(declared_amount=Decimal("1000"))
    attempt = PaymentAttempt(provider="gw", provider_reference="r1", amount=Decimal("1000"), state=AttemptState.CONFIRMED)

    res = TruthEngine.resolve(
        intent=intent,
        attempts=[attempt],
        events=[],
        links=[],
        causal_chain=[RootCauseRuleResult(rule_id=RootCauseType.RC_UNKNOWN, name="", description="", matched=True, severity="LOW", confidence_impact=1.0, recommended_action="")]
    )

    assert res.resolution_state == ResolutionState.SAFE_TO_COMMIT
    assert res.intent_state == IntentState.CONFIRMED
    assert res.observed_amount == Decimal("1000.00")
    assert res.candidate_amount == Decimal("1000.00")
    assert res.committed_amount == Decimal("0.00")  # Zero committed until ledger write path executes!

def test_truth_engine_canonical_network_timeout_retry():
    intent = PaymentIntent(declared_amount=Decimal("2000"))
    attempt_a = PaymentAttempt(provider="gw_a", provider_reference="r1", amount=Decimal("2000"), state=AttemptState.CONFIRMED)
    attempt_b = PaymentAttempt(provider="gw_b", provider_reference="r2", amount=Decimal("2000"), state=AttemptState.CONFIRMED)

    res = TruthEngine.resolve(
        intent=intent,
        attempts=[attempt_a, attempt_b],
        events=[],
        links=[],
        causal_chain=[RootCauseRuleResult(rule_id=RootCauseType.RC_NETWORK_TIMEOUT, name="", description="", matched=True, severity="HIGH", confidence_impact=0.95, recommended_action="")]
    )

    assert res.resolution_state == ResolutionState.HELD_FOR_REVIEW
    assert res.intent_state == IntentState.POTENTIAL_DUPLICATE
    assert res.observed_amount == Decimal("4000.00")
    assert res.candidate_amount == Decimal("2000.00")
    assert res.committed_amount == Decimal("0.00")  # Zero committed automatically!

def test_truth_engine_provider_contradiction():
    intent = PaymentIntent(declared_amount=Decimal("3000"))
    attempt = PaymentAttempt(provider="gw", provider_reference="r1", amount=Decimal("3000"), state=AttemptState.FAILED)

    res = TruthEngine.resolve(
        intent=intent,
        attempts=[attempt],
        events=[],
        links=[],
        causal_chain=[RootCauseRuleResult(rule_id=RootCauseType.RC_CONFLICTING_PROVIDER, name="", description="", matched=True, severity="HIGH", confidence_impact=0.5, recommended_action="")]
    )

    assert res.resolution_state == ResolutionState.CONFLICTING_STATE
    assert res.intent_state == IntentState.CONFLICTING_STATE
    assert res.committed_amount == Decimal("0.00")
