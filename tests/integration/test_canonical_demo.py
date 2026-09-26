from decimal import Decimal
import pytest

def test_canonical_demo_flow(client):
    # Trigger Canonical simulation
    sim_res = client.post("/api/simulations/CANONICAL_DEMO/run?seed=42")
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    snap = sim_data["resolution_snapshot"]
    intent_id = snap["intent_id"]

    # Assert Canonical initial state (Section 18 & 35)
    assert snap["intent_state"] == "POTENTIAL_DUPLICATE"
    assert snap["observed_amount"] == 4000.0
    assert snap["candidate_amount"] == 2000.0
    assert snap["committed_amount"] == 0.0

    # Fetch incident detail to retrieve candidate attempt IDs
    inc_res = client.get(f"/api/incidents/{intent_id}")
    assert inc_res.status_code == 200
    inc_data = inc_res.json()

    candidates = inc_data["resolution"]["candidate_attempt_ids"]
    assert len(candidates) >= 1
    chosen_attempt_id = candidates[0]

    # Reviewer confirms one attempt
    review_req = {
        "decision": "CONFIRM_ATTEMPT",
        "chosen_attempt_id": chosen_attempt_id,
        "reviewer_note": "Confirmed legitimate payment attempt after checking gateway B bank statement."
    }
    rev_res = client.post(f"/api/incidents/{intent_id}/review", json=review_req)
    assert rev_res.status_code == 200
    rev_data = rev_res.json()
    assert rev_data["status"] == "SUCCESS"
    tx_id = rev_data["financial_transaction_id"]

    # Verify FinancialTransaction committed ₹2,000
    tx_res = client.get(f"/api/transactions/{intent_id}")
    assert tx_res.status_code == 200
    tx_data = tx_res.json()
    assert float(tx_data["amount"]) == 2000.0

    # Verify Explain endpoint output
    exp_res = client.post(f"/api/transactions/{intent_id}/explain")
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert "Primary Cause:" in exp_data["explanation_text"]
