from decimal import Decimal
from datetime import datetime, timezone
from hypothesis import given, settings, HealthCheck, strategies as st
import pytest

from app.schemas.schemas import EventIngestionRequest
from app.services.ingestion_service import IngestionService

@given(
    amount=st.decimals(min_value=Decimal("1.00"), max_value=Decimal("10000.00"), places=2),
    ref_suffix=st.text(min_size=1, max_size=10, alphabet="0123456789abcdef")
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_hypothesis_invariant_i1_idempotency(db_session, amount, ref_suffix):
    service = IngestionService(db_session)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    req = EventIngestionRequest(
        provider="gw_prop",
        provider_reference=f"REF-PROP-{ref_suffix}",
        event_type="GATEWAY_CONFIRMED",
        amount=amount,
        currency="INR",
        order_id=f"ORD-PROP-{ref_suffix}",
        customer_id="CUST-PROP",
        event_created_at=now,
        raw_payload={"amt": float(amount)}
    )

    res1 = service.ingest_event(req)
    res2 = service.ingest_event(req)

    # Invariant I1: process(events) == process(events + duplicate)
    assert res1.is_duplicate is False
    assert res2.is_duplicate is True
    assert res1.dedup_hash == res2.dedup_hash
