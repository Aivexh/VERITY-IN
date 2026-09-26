from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, update, func, or_

from app.models.models import (
    PaymentIntent, PaymentAttempt, PaymentEvent, TransactionLink,
    FinancialResolution, FinancialTransaction, IncidentAnalysis,
    AuditLog, SimulationRun
)
from app.domain.enums import IntentState, AttemptState

class PaymentIntentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, intent_id: UUID) -> Optional[PaymentIntent]:
        stmt = (
            select(PaymentIntent)
            .where(PaymentIntent.id == intent_id)
            .options(
                joinedload(PaymentIntent.attempts).joinedload(PaymentAttempt.events),
                joinedload(PaymentIntent.resolutions),
                joinedload(PaymentIntent.incident_analyses)
            )
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def get_by_order_id(self, order_id: str) -> Optional[PaymentIntent]:
        stmt = (
            select(PaymentIntent)
            .where(PaymentIntent.order_id == order_id)
            .options(joinedload(PaymentIntent.attempts))
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def create(self, intent: PaymentIntent) -> PaymentIntent:
        self.db.add(intent)
        self.db.flush()
        return intent

    def update_state(self, intent_id: UUID, new_state: IntentState) -> Optional[PaymentIntent]:
        intent = self.db.query(PaymentIntent).filter(PaymentIntent.id == intent_id).first()
        if intent:
            intent.aggregate_state = new_state
            self.db.flush()
        return intent

    def list_all(self, limit: int = 50, offset: int = 0) -> List[PaymentIntent]:
        stmt = select(PaymentIntent).order_by(PaymentIntent.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())


class PaymentAttemptRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, attempt_id: UUID) -> Optional[PaymentAttempt]:
        stmt = (
            select(PaymentAttempt)
            .where(PaymentAttempt.id == attempt_id)
            .options(joinedload(PaymentAttempt.events))
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def get_by_provider_reference(self, provider: str, provider_reference: str) -> Optional[PaymentAttempt]:
        stmt = (
            select(PaymentAttempt)
            .where(PaymentAttempt.provider_reference == provider_reference)
            .options(joinedload(PaymentAttempt.events))
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def create(self, attempt: PaymentAttempt) -> PaymentAttempt:
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def update_state(self, attempt_id: UUID, next_state: AttemptState) -> Optional[PaymentAttempt]:
        attempt = self.db.query(PaymentAttempt).filter(PaymentAttempt.id == attempt_id).first()
        if attempt:
            attempt.state = next_state
            self.db.flush()
        return attempt

    def get_attempts_for_intent(self, intent_id: UUID) -> List[PaymentAttempt]:
        stmt = (
            select(PaymentAttempt)
            .where(PaymentAttempt.intent_id == intent_id)
            .options(joinedload(PaymentAttempt.events))
            .order_by(PaymentAttempt.created_at.asc())
        )
        return list(self.db.execute(stmt).unique().scalars().all())

    def get_candidate_attempts(self, order_id: Optional[str], customer_id: Optional[str], provider_ref: Optional[str]) -> List[PaymentAttempt]:
        query = select(PaymentAttempt).join(PaymentIntent, PaymentAttempt.intent_id == PaymentIntent.id, isouter=True)
        conditions = []
        if order_id:
            conditions.append(PaymentIntent.order_id == order_id)
        if customer_id:
            conditions.append(PaymentIntent.customer_id == customer_id)
        if provider_ref:
            conditions.append(PaymentAttempt.provider_reference == provider_ref)

        if not conditions:
            return []

        stmt = query.where(or_(*conditions)).options(joinedload(PaymentAttempt.events))
        return list(self.db.execute(stmt).unique().scalars().all())


class PaymentEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_dedup_hash(self, dedup_hash: str) -> Optional[PaymentEvent]:
        stmt = select(PaymentEvent).where(PaymentEvent.dedup_hash == dedup_hash)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, event: PaymentEvent) -> PaymentEvent:
        self.db.add(event)
        self.db.flush()
        return event

    def get_events_for_attempt(self, attempt_id: UUID) -> List[PaymentEvent]:
        stmt = select(PaymentEvent).where(PaymentEvent.attempt_id == attempt_id).order_by(PaymentEvent.event_created_at.asc())
        return list(self.db.execute(stmt).scalars().all())

    def get_events_for_intent(self, intent_id: UUID) -> List[PaymentEvent]:
        stmt = (
            select(PaymentEvent)
            .join(PaymentAttempt, PaymentEvent.attempt_id == PaymentAttempt.id)
            .where(PaymentAttempt.intent_id == intent_id)
            .order_by(PaymentEvent.event_created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())


class TransactionLinkRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, link: TransactionLink) -> TransactionLink:
        self.db.add(link)
        self.db.flush()
        return link

    def get_links_for_attempt(self, attempt_id: UUID) -> List[TransactionLink]:
        stmt = select(TransactionLink).where(
            (TransactionLink.source_attempt_id == attempt_id) |
            (TransactionLink.target_attempt_id == attempt_id)
        )
        return list(self.db.execute(stmt).scalars().all())


class FinancialResolutionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, resolution: FinancialResolution) -> FinancialResolution:
        self.db.add(resolution)
        self.db.flush()
        return resolution

    def get_latest_for_intent(self, intent_id: UUID) -> Optional[FinancialResolution]:
        stmt = (
            select(FinancialResolution)
            .where(FinancialResolution.intent_id == intent_id)
            .order_by(FinancialResolution.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()


class FinancialTransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_intent_id(self, intent_id: UUID) -> Optional[FinancialTransaction]:
        stmt = select(FinancialTransaction).where(FinancialTransaction.intent_id == intent_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, tx: FinancialTransaction) -> FinancialTransaction:
        self.db.add(tx)
        self.db.flush()
        return tx

    def list_all(self, limit: int = 50, offset: int = 0) -> List[FinancialTransaction]:
        stmt = select(FinancialTransaction).order_by(FinancialTransaction.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())


class IncidentAnalysisRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, analysis: IncidentAnalysis) -> IncidentAnalysis:
        self.db.add(analysis)
        self.db.flush()
        return analysis

    def get_by_intent_id(self, intent_id: UUID) -> Optional[IncidentAnalysis]:
        stmt = (
            select(IncidentAnalysis)
            .where(IncidentAnalysis.intent_id == intent_id)
            .order_by(IncidentAnalysis.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, log: AuditLog) -> AuditLog:
        self.db.add(log)
        self.db.flush()
        return log

    def get_logs_for_entity(self, entity_type: str, entity_id: str) -> List[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type)
            .where(AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())


class SimulationRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, sim: SimulationRun) -> SimulationRun:
        self.db.add(sim)
        self.db.flush()
        return sim

    def get_by_id(self, sim_id: UUID) -> Optional[SimulationRun]:
        stmt = select(SimulationRun).where(SimulationRun.id == sim_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_status(self, sim_id: UUID, status: str, completed_at: Optional[datetime] = None, snapshot: Optional[dict] = None) -> Optional[SimulationRun]:
        sim = self.db.query(SimulationRun).filter(SimulationRun.id == sim_id).first()
        if sim:
            sim.status = status
            if completed_at:
                sim.completed_at = completed_at
            if snapshot is not None:
                sim.resolution_snapshot = snapshot
            self.db.flush()
        return sim
