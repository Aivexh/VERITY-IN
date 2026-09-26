from datetime import datetime, timezone
from decimal import Decimal
import pytest

def test_full_event_ingestion_pipeline(client):
    req_payload = {
        "provider": "gateway_a",
        "provider_reference": "REF-INTEG-1",
        "event_type": "GATEWAY_CONFIRMED",
        "amount": 2500.00,
        "currency": "INR",
        "order_id": "ORD-INTEG-1",
        "customer_id": "CUST-INTEG-1",
        "event_created_at": datetime.now(timezone.utc).isoformat(),
        "raw_payload": {"status": "CONFIRMED"}
    }

    response = client.post("/api/events", json=req_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_duplicate"] is False
    assert data["status"] == "PROCESSED"
    intent_id = data["intent_id"]

    # Re-ingest exact same payload (Idempotency check)
    dup_res = client.post("/api/events", json=req_payload)
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["is_duplicate"] is True
    assert dup_data["status"] == "IDEMPOTENT_NOOP"

    # Query Dashboard
    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["total_events"] >= 1
