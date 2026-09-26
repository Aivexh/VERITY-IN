from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

def test_a1_normal_success(client):
    req = {
        "provider": "gateway_a",
        "provider_reference": "REF-A1",
        "event_type": "GATEWAY_CONFIRMED",
        "amount": 1000.00,
        "currency": "INR",
        "order_id": "ORD-A1",
        "customer_id": "CUST-A1",
        "event_created_at": datetime.now(timezone.utc).isoformat(),
        "raw_payload": {"amount": 1000.0}
    }
    res = client.post("/api/events", json=req)
    assert res.status_code == 200
    intent_id = res.json()["intent_id"]

    inc_res = client.get(f"/api/incidents/{intent_id}")
    assert inc_res.status_code == 200
    detail = inc_res.json()
    assert detail["summary"]["aggregate_state"] == "CONFIRMED"

def test_a2_duplicate_webhook(client):
    req = {
        "provider": "gateway_a",
        "provider_reference": "REF-A2",
        "event_type": "GATEWAY_CONFIRMED",
        "amount": 1000.00,
        "currency": "INR",
        "order_id": "ORD-A2",
        "customer_id": "CUST-A2",
        "event_created_at": datetime.now(timezone.utc).isoformat(),
        "raw_payload": {"amount": 1000.0}
    }
    r1 = client.post("/api/events", json=req)
    r2 = client.post("/api/events", json=req)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["is_duplicate"] is True

def test_a3_delayed_webhook(client):
    base = datetime.now(timezone.utc) - timedelta(seconds=120)
    req = {
        "provider": "gateway_a",
        "provider_reference": "REF-A3",
        "event_type": "GATEWAY_CONFIRMED",
        "amount": 1000.00,
        "currency": "INR",
        "order_id": "ORD-A3",
        "customer_id": "CUST-A3",
        "event_created_at": base.isoformat(),
        "raw_payload": {"amount": 1000.0}
    }
    res = client.post("/api/events", json=req)
    assert res.status_code == 200
    intent_id = res.json()["intent_id"]

    analysis = client.get(f"/api/transactions/{intent_id}/analysis").json()
    causes = [c["rule_id"] for c in analysis["root_cause_chain"]]
    assert "RC_DELAYED_WEBHOOK" in causes

def test_a5_timeout_and_retry(client):
    res = client.post("/api/simulations/NETWORK_TIMEOUT_RETRY/run?seed=100")
    assert res.status_code == 200
    data = res.json()
    snap = data["resolution_snapshot"]
    assert snap["intent_state"] == "POTENTIAL_DUPLICATE"
    assert snap["observed_amount"] == 4000.0
    assert snap["candidate_amount"] == 2000.0
    assert snap["committed_amount"] == 0.0

def test_a7_conflicting_providers(client):
    res = client.post("/api/simulations/CONFLICTING_PROVIDER/run?seed=200")
    assert res.status_code == 200
    data = res.json()
    snap = data["resolution_snapshot"]
    assert snap["intent_state"] == "CONFLICTING_STATE"
    assert snap["committed_amount"] == 0.0
