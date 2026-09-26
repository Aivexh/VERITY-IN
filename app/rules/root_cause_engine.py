import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.domain.enums import RootCauseType
from app.models.models import PaymentEvent, PaymentAttempt, PaymentIntent

class RootCauseRuleResult(BaseModel):
    rule_id: RootCauseType
    name: str
    description: str
    matched: bool
    severity: str  # HIGH, MEDIUM, LOW
    confidence_impact: float
    recommended_action: str
    details: Dict[str, Any] = {}


class RootCauseEngine:
    SEVERITY_ORDER = {
        RootCauseType.RC_CONFLICTING_PROVIDER: 1,
        RootCauseType.RC_NETWORK_TIMEOUT: 2,
        RootCauseType.RC_DUPLICATE_WEBHOOK: 3,
        RootCauseType.RC_OUT_OF_ORDER: 4,
        RootCauseType.RC_DELAYED_WEBHOOK: 5,
        RootCauseType.RC_CUSTOMER_RETRY: 6,
        RootCauseType.RC_MISSING_EVENT: 7,
        RootCauseType.RC_UNKNOWN: 8,
    }

    @staticmethod
    def evaluate(
        intent: PaymentIntent,
        attempts: List[PaymentAttempt],
        events: List[PaymentEvent],
        has_duplicate_hash: bool = False
    ) -> List[RootCauseRuleResult]:
        matched_rules: List[RootCauseRuleResult] = []

        now_utc = datetime.now(timezone.utc)
        for e in events:
            if getattr(e, "id", None) is None:
                e.id = uuid.uuid4()
            if getattr(e, "event_received_at", None) is None:
                e.event_received_at = now_utc

        for a in attempts:
            if getattr(a, "id", None) is None:
                a.id = uuid.uuid4()

        # Rule 1: RC_DUPLICATE_WEBHOOK
        if has_duplicate_hash:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_DUPLICATE_WEBHOOK,
                name="Duplicate Webhook Delivery",
                description="Identical SHA-256 event dedup hash received multiple times.",
                matched=True,
                severity="MEDIUM",
                confidence_impact=0.9,
                recommended_action="IDEMPOTENT_NOOP"
            ))

        # Rule 2: RC_OUT_OF_ORDER
        sorted_created = sorted(events, key=lambda e: e.event_created_at)
        sorted_received = sorted(events, key=lambda e: e.event_received_at)

        created_ids = [e.id for e in sorted_created]
        received_ids = [e.id for e in sorted_received]

        if created_ids != received_ids and len(events) > 1:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_OUT_OF_ORDER,
                name="Out-of-Order Webhook Delivery",
                description="Event received_at ordering disagrees with provider event_created_at ordering.",
                matched=True,
                severity="MEDIUM",
                confidence_impact=0.85,
                recommended_action="REORDER_TIMELINE",
                details={"created_order": [str(i) for i in created_ids], "received_order": [str(i) for i in received_ids]}
            ))

        # Rule 3: RC_DELAYED_WEBHOOK
        delayed_events = [e for e in events if (e.event_received_at - e.event_created_at).total_seconds() > 30]
        if delayed_events:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_DELAYED_WEBHOOK,
                name="Delayed Webhook Delivery",
                description=f"Webhook received with excessive delivery lag (> 30s) for {len(delayed_events)} events.",
                matched=True,
                severity="MEDIUM",
                confidence_impact=0.85,
                recommended_action="CORRELATE_RETRIES",
                details={"delayed_count": len(delayed_events)}
            ))

        # Rule 4: RC_NETWORK_TIMEOUT
        has_bank_success = any(e.event_type == "BANK_SUCCESS" for e in events)
        has_timeout_event = any(e.event_type in ("TIMED_OUT", "TIMEOUT_DETECTED") for e in events)
        if (has_bank_success and has_timeout_event) or (has_timeout_event and len(attempts) > 1):
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_NETWORK_TIMEOUT,
                name="Network Timeout During Confirmation",
                description="Bank succeeded but confirmation was lost or timed out, triggering retry.",
                matched=True,
                severity="HIGH",
                confidence_impact=0.95,
                recommended_action="MANUAL_REVIEW"
            ))

        # Rule 5: RC_CUSTOMER_RETRY
        if len(attempts) > 1:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_CUSTOMER_RETRY,
                name="Customer Payment Retry",
                description=f"Customer initiated {len(attempts)} distinct payment attempts for single intent.",
                matched=True,
                severity="MEDIUM",
                confidence_impact=0.9,
                recommended_action="HELD_FOR_REVIEW",
                details={"attempt_count": len(attempts)}
            ))

        # Rule 6: RC_CONFLICTING_PROVIDER (Contradiction across bank vs gateway or success vs failure)
        has_success = any(e.event_type in ("BANK_SUCCESS", "GATEWAY_CONFIRMED", "CONFIRMED") for e in events)
        has_failed = any(e.event_type in ("BANK_FAILED", "GATEWAY_FAILED", "FAILED") for e in events)
        if has_success and has_failed:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_CONFLICTING_PROVIDER,
                name="Conflicting Provider Observation",
                description="Contradictory success vs failure events for the same payment intent.",
                matched=True,
                severity="HIGH",
                confidence_impact=0.95,
                recommended_action="FLAG_CONFLICTING_STATE"
            ))

        # Rule 7: RC_MISSING_EVENT
        if len(events) == 1 and events[0].event_type == "INITIATED":
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_MISSING_EVENT,
                name="Missing Provider Confirmation",
                description="Payment attempt initiated but no subsequent status webhook received.",
                matched=True,
                severity="LOW",
                confidence_impact=0.5,
                recommended_action="WAIT_FOR_WEBHOOK"
            ))

        # Fallback if no rules matched
        if not matched_rules:
            matched_rules.append(RootCauseRuleResult(
                rule_id=RootCauseType.RC_UNKNOWN,
                name="Unknown / Standard Processing",
                description="Standard payment observation pattern.",
                matched=True,
                severity="LOW",
                confidence_impact=1.0,
                recommended_action="AUTO_PROCESS"
            ))

        # Sort causal chain by severity priority
        matched_rules.sort(key=lambda r: RootCauseEngine.SEVERITY_ORDER.get(r.rule_id, 99))
        return matched_rules

    @staticmethod
    def select_primary_cause(causal_chain: List[RootCauseRuleResult]) -> RootCauseType:
        if not causal_chain:
            return RootCauseType.RC_UNKNOWN
        return causal_chain[0].rule_id
