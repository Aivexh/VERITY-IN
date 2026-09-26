import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.schemas.schemas import EventIngestionRequest, SimulationRunResponse
from app.services.ingestion_service import IngestionService
from app.repositories.repositories import SimulationRunRepository, PaymentIntentRepository, FinancialResolutionRepository
from app.models.models import SimulationRun

class SimulationEngine:
    def __init__(self, db: Session):
        self.db = db
        self.ingestion_service = IngestionService(db)
        self.sim_repo = SimulationRunRepository(db)
        self.intent_repo = PaymentIntentRepository(db)
        self.res_repo = FinancialResolutionRepository(db)

    def run_scenario(self, scenario_id: str, seed: int = 42) -> SimulationRunResponse:
        base_time = datetime(2026, 9, 26, 10, 31, 0, tzinfo=timezone.utc) + timedelta(seconds=(seed % 100))
        sim = SimulationRun(
            scenario_id=scenario_id,
            seed=seed,
            generated_event_hash="pending",
            status="RUNNING"
        )
        sim = self.sim_repo.create(sim)

        events_to_ingest: List[EventIngestionRequest] = []
        order_id = f"ORD-SIM-{scenario_id}-{seed}"
        cust_id = f"CUST-SIM-{seed}"

        if scenario_id == "CANONICAL_DEMO" or scenario_id == "NETWORK_TIMEOUT_RETRY":
            # Scenario 18 & 35 Canonical Story
            # 10:31:05 Gateway A INITIATED ₹2,000
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-A-{seed}",
                event_type="INITIATED",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=1,
                event_created_at=base_time + timedelta(seconds=5),
                raw_payload={"amount": 2000.0, "status": "INITIATED"}
            ))
            # 10:31:20 Bank A SUCCESS ₹2,000
            events_to_ingest.append(EventIngestionRequest(
                provider="bank_a",
                provider_reference=f"REF-A-{seed}",
                event_type="BANK_SUCCESS",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=1,
                event_created_at=base_time + timedelta(seconds=20),
                raw_payload={"amount": 2000.0, "status": "SUCCESS"}
            ))
            # 10:31:46 TIMEOUT_DETECTED
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-A-{seed}",
                event_type="TIMED_OUT",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=1,
                event_created_at=base_time + timedelta(seconds=46),
                raw_payload={"amount": 2000.0, "status": "TIMED_OUT"}
            ))
            # 10:31:53 Gateway B INITIATED ₹2,000
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_b",
                provider_reference=f"REF-B-{seed}",
                event_type="INITIATED",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=2,
                event_created_at=base_time + timedelta(seconds=53),
                raw_payload={"amount": 2000.0, "status": "INITIATED"}
            ))
            # 10:32:02 Bank B SUCCESS ₹2,000
            events_to_ingest.append(EventIngestionRequest(
                provider="bank_b",
                provider_reference=f"REF-B-{seed}",
                event_type="BANK_SUCCESS",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=2,
                event_created_at=base_time + timedelta(seconds=62),
                raw_payload={"amount": 2000.0, "status": "SUCCESS"}
            ))
            # 10:32:10 Gateway B CONFIRMED
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_b",
                provider_reference=f"REF-B-{seed}",
                event_type="GATEWAY_CONFIRMED",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=2,
                event_created_at=base_time + timedelta(seconds=70),
                raw_payload={"amount": 2000.0, "status": "CONFIRMED"}
            ))
            # 10:32:40 Delayed Gateway A confirmation
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-A-{seed}",
                event_type="GATEWAY_CONFIRMED",
                amount=2000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                merchant_session_id=f"SESS-{seed}",
                attempt_sequence_hint=1,
                event_created_at=base_time + timedelta(seconds=30),  # Provider created at 10:31:30, but received late!
                raw_payload={"amount": 2000.0, "status": "CONFIRMED"}
            ))

        elif scenario_id == "NORMAL_SUCCESS":
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-NORM-{seed}",
                event_type="INITIATED",
                amount=1500.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time,
                raw_payload={"amount": 1500.0, "status": "INITIATED"}
            ))
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-NORM-{seed}",
                event_type="GATEWAY_CONFIRMED",
                amount=1500.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time + timedelta(seconds=10),
                raw_payload={"amount": 1500.0, "status": "CONFIRMED"}
            ))

        elif scenario_id == "DUPLICATE_WEBHOOK":
            req = EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-DUP-{seed}",
                event_type="GATEWAY_CONFIRMED",
                amount=1000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time,
                raw_payload={"amount": 1000.0, "status": "CONFIRMED"}
            )
            events_to_ingest.append(req)
            events_to_ingest.append(req)  # Identical duplicate event!

        elif scenario_id == "CONFLICTING_PROVIDER":
            events_to_ingest.append(EventIngestionRequest(
                provider="bank_a",
                provider_reference=f"REF-CONF-{seed}",
                event_type="BANK_SUCCESS",
                amount=3000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time,
                raw_payload={"amount": 3000.0}
            ))
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-CONF-{seed}",
                event_type="GATEWAY_FAILED",
                amount=3000.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time + timedelta(seconds=5),
                raw_payload={"amount": 3000.0}
            ))

        else:
            # Default fallback scenario
            events_to_ingest.append(EventIngestionRequest(
                provider="gateway_a",
                provider_reference=f"REF-GEN-{seed}",
                event_type="INITIATED",
                amount=500.00,
                currency="INR",
                order_id=order_id,
                customer_id=cust_id,
                event_created_at=base_time,
                raw_payload={"amount": 500.0}
            ))

        # Run generated events through the real ingestion pipeline!
        hashes = []
        last_intent_id: Optional[UUID] = None
        for req in events_to_ingest:
            res = self.ingestion_service.ingest_event(req)
            hashes.append(res.dedup_hash)
            if res.intent_id:
                last_intent_id = res.intent_id

        combined_hash = hashlib.sha256("".join(hashes).encode()).hexdigest()

        # Capture snapshot
        snapshot = {}
        if last_intent_id:
            resolution = self.res_repo.get_latest_for_intent(last_intent_id)
            intent = self.intent_repo.get_by_id(last_intent_id)
            if resolution and intent:
                snapshot = {
                    "intent_id": str(last_intent_id),
                    "intent_state": intent.aggregate_state.value,
                    "observed_amount": float(resolution.observed_amount),
                    "candidate_amount": float(resolution.candidate_amount),
                    "committed_amount": float(resolution.committed_amount),
                    "resolution_state": resolution.resolution_state.value
                }

        sim.generated_event_hash = combined_hash
        sim.status = "COMPLETED"
        sim.completed_at = datetime.now(timezone.utc)
        sim.resolution_snapshot = snapshot

        self.db.commit()

        return SimulationRunResponse(
            id=sim.id,
            scenario_id=sim.scenario_id,
            seed=sim.seed,
            generated_event_hash=sim.generated_event_hash,
            status=sim.status,
            started_at=sim.started_at,
            completed_at=sim.completed_at,
            resolution_snapshot=sim.resolution_snapshot,
            engine_version=sim.engine_version
        )
