import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Numeric, DateTime, Enum as SQLEnum, ForeignKey,
    UniqueConstraint, Index, Integer, Text, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.config.database import Base
from app.domain.enums import (
    AttemptState, IntentState, CorrelationRelation, ResolutionState
)

# Use standard JSON fallback for portability if SQLite is used in tests, but default to JSON/JSONB
JsonType = JSON

class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String(255), nullable=False, index=True)
    customer_id = Column(String(255), nullable=False, index=True)
    declared_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    aggregate_state = Column(SQLEnum(IntentState), nullable=False, default=IntentState.PENDING, index=True)
    resolved_financial_transaction_id = Column(UUID(as_uuid=True), ForeignKey("financial_transactions.id", use_alter=True, name="fk_payment_intents_transaction_id"), nullable=True)

    attempts = relationship("PaymentAttempt", back_populates="intent", cascade="all, delete-orphan")
    resolutions = relationship("FinancialResolution", back_populates="intent", cascade="all, delete-orphan")
    financial_transaction = relationship("FinancialTransaction", foreign_keys=[resolved_financial_transaction_id], post_update=True)
    incident_analyses = relationship("IncidentAnalysis", back_populates="intent", cascade="all, delete-orphan")


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_provider_reference"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id = Column(UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=True, index=True)
    provider = Column(String(100), nullable=False, index=True)
    provider_reference = Column(String(255), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    payment_method = Column(String(100), nullable=True)
    merchant_session_id = Column(String(255), nullable=True)
    attempt_sequence_hint = Column(Integer, nullable=True)
    state = Column(SQLEnum(AttemptState), nullable=False, default=AttemptState.INITIATED)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    intent = relationship("PaymentIntent", back_populates="attempts")
    events = relationship("PaymentEvent", back_populates="attempt", cascade="all, delete-orphan")


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_event_dedup_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    provider = Column(String(100), nullable=False, index=True)
    event_created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    event_received_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    raw_payload = Column(JsonType, nullable=False)
    dedup_hash = Column(String(64), nullable=False, index=True)

    attempt = relationship("PaymentAttempt", back_populates="events")


class TransactionLink(Base):
    __tablename__ = "transaction_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    target_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False, index=True)
    relation = Column(SQLEnum(CorrelationRelation), nullable=False)
    correlation_score = Column(Integer, nullable=False)
    correlation_evidence = Column(JsonType, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FinancialResolution(Base):
    __tablename__ = "financial_resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id = Column(UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=False, index=True)
    observed_amount = Column(Numeric(12, 2), nullable=False)
    candidate_amount = Column(Numeric(12, 2), nullable=False)
    committed_amount = Column(Numeric(12, 2), nullable=False, default=0)
    resolution_state = Column(SQLEnum(ResolutionState), nullable=False, index=True)
    selected_attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=True)
    candidate_attempt_ids = Column(JsonType, nullable=False)
    resolution_confidence = Column(Numeric(5, 4), nullable=False)
    reason = Column(Text, nullable=False)
    evidence = Column(JsonType, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    intent = relationship("PaymentIntent", back_populates="resolutions")


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (
        UniqueConstraint("intent_id", name="uq_financial_transaction_intent_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id = Column(UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=False, index=True)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("payment_attempts.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class IncidentAnalysis(Base):
    __tablename__ = "incident_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id = Column(UUID(as_uuid=True), ForeignKey("payment_intents.id"), nullable=False, index=True)
    root_cause_chain = Column(JsonType, nullable=False)
    correlation_evidence = Column(JsonType, nullable=False)
    resolution = Column(JsonType, nullable=False)
    recommendation = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    intent = relationship("PaymentIntent", back_populates="incident_analyses")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(String(255), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    actor = Column(String(100), nullable=False, default="SYSTEM")
    details = Column(JsonType, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id = Column(String(100), nullable=False, index=True)
    seed = Column(Integer, nullable=False)
    generated_event_hash = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    resolution_snapshot = Column(JsonType, nullable=True)
    engine_version = Column(String(50), nullable=False, default="1.0.0")
