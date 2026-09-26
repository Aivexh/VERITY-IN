from uuid import UUID
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.models import PaymentIntent, PaymentAttempt, FinancialTransaction, FinancialResolution
from app.domain.enums import IntentState, AttemptState, ResolutionState
from app.services.audit_service import AuditService

class LedgerCommitError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def create_financial_transaction(db: Session, intent_id: UUID, attempt_id: UUID, actor: str = "SYSTEM") -> FinancialTransaction:
    """
    INVARIANT I8 / I9 — SINGLE LEDGER WRITE PATH.
    The ONLY function authorized to insert into financial_transactions.
    """
    audit_service = AuditService(db)

    # 1. SELECT intent FOR UPDATE to lock row concurrently
    intent = db.query(PaymentIntent).filter(PaymentIntent.id == intent_id).with_for_update().first()
    if not intent:
        raise LedgerCommitError(f"Payment intent {intent_id} not found", status_code=444)

    # 2. Check existing FinancialTransaction
    existing_tx = db.query(FinancialTransaction).filter(FinancialTransaction.intent_id == intent_id).first()
    if existing_tx:
        raise LedgerCommitError(f"Financial transaction already exists for intent {intent_id}", status_code=409)

    # 3. Verify current intent state permits commitment (Invariants I3 & I7)
    intent_state_str = str(intent.aggregate_state.value if hasattr(intent.aggregate_state, "value") else intent.aggregate_state)
    if intent_state_str in ("POTENTIAL_DUPLICATE", "CONFLICTING_STATE", "INSUFFICIENT_EVIDENCE", "MANUAL_REVIEW"):
        if actor == "SYSTEM":
            raise LedgerCommitError(
                f"Intent state {intent_state_str} cannot auto-commit financial transaction without reviewer resolution.",
                status_code=409
            )

    # 4. Verify chosen attempt belongs to intent
    attempt = db.query(PaymentAttempt).filter(PaymentAttempt.id == attempt_id, PaymentAttempt.intent_id == intent_id).first()
    if not attempt:
        raise LedgerCommitError(f"Payment attempt {attempt_id} does not belong to intent {intent_id}", status_code=400)

    # 5. Verify chosen attempt is eligible (must be in a confirmed state)
    attempt_state_str = str(attempt.state.value if hasattr(attempt.state, "value") else attempt.state)
    if attempt_state_str not in ("CONFIRMED", "GATEWAY_CONFIRMED", "BANK_SUCCESS"):
        raise LedgerCommitError(f"Payment attempt state {attempt_state_str} is not eligible for financial commitment", status_code=400)

    try:
        # 6. INSERT FinancialTransaction
        tx = FinancialTransaction(
            intent_id=intent_id,
            attempt_id=attempt_id,
            amount=attempt.amount,
            currency=attempt.currency
        )
        db.add(tx)
        db.flush()

        # 7. UPDATE PaymentIntent reference and state
        intent.resolved_financial_transaction_id = tx.id
        intent.aggregate_state = IntentState.CONFIRMED

        # Update latest resolution to COMMITTED state if exists
        resolution = db.query(FinancialResolution).filter(FinancialResolution.intent_id == intent_id).order_by(FinancialResolution.created_at.desc()).first()
        if resolution:
            resolution.committed_amount = attempt.amount
            resolution.resolution_state = ResolutionState.COMMITTED
            resolution.selected_attempt_id = attempt_id

        # 8. AUDIT RECORD
        audit_service.log_event(
            entity_type="FinancialTransaction",
            entity_id=tx.id,
            action="CREATE_LEDGER_TRANSACTION",
            actor=actor,
            details={
                "intent_id": str(intent_id),
                "attempt_id": str(attempt_id),
                "amount": float(attempt.amount),
                "currency": attempt.currency
            }
        )

        # 9. COMMIT DB TRANSACTION
        db.commit()
        db.refresh(tx)
        return tx

    except Exception as e:
        db.rollback()
        audit_service.log_event(
            entity_type="PaymentIntent",
            entity_id=intent_id,
            action="LEDGER_COMMIT_FAILED",
            actor=actor,
            details={"error": str(e), "attempt_id": str(attempt_id)}
        )
        db.commit()
        if isinstance(e, LedgerCommitError):
            raise e
        raise LedgerCommitError(f"Unrecoverable database failure during transaction creation: {str(e)}", status_code=500)
