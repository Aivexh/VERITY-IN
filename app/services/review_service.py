from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.enums import ReviewDecision, IntentState
from app.schemas.schemas import ReviewRequest
from app.repositories.repositories import PaymentIntentRepository, PaymentAttemptRepository, FinancialResolutionRepository
from app.state_machine.state_machine import StateMachine
from app.services.audit_service import AuditService
from app.services.ledger_service import create_financial_transaction, LedgerCommitError

class ReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.intent_repo = PaymentIntentRepository(db)
        self.attempt_repo = PaymentAttemptRepository(db)
        self.resolution_repo = FinancialResolutionRepository(db)
        self.audit_service = AuditService(db)

    def process_review(self, intent_id: UUID, request: ReviewRequest, reviewer_id: str = "REVIEWER_1") -> dict:
        intent = self.intent_repo.get_by_id(intent_id)
        if not intent:
            raise HTTPException(status_code=444, detail=f"Incident / Intent {intent_id} not found")

        # Validate transition privilege
        StateMachine.validate_intent_transition(intent.aggregate_state, IntentState.CONFIRMED, is_reviewer=True)

        if request.decision == ReviewDecision.CONFIRM_ATTEMPT:
            if not request.chosen_attempt_id:
                raise HTTPException(status_code=400, detail="chosen_attempt_id is required for CONFIRM_ATTEMPT decision")

            chosen_attempt = self.attempt_repo.get_by_id(request.chosen_attempt_id)
            if not chosen_attempt or chosen_attempt.intent_id != intent_id:
                raise HTTPException(status_code=400, detail="chosen_attempt_id does not belong to this intent")

            # Audit reviewer decision
            self.audit_service.log_event(
                entity_type="PaymentIntent",
                entity_id=intent_id,
                action="REVIEWER_CONFIRM_ATTEMPT",
                actor=reviewer_id,
                details={
                    "chosen_attempt_id": str(request.chosen_attempt_id),
                    "reviewer_note": request.reviewer_note,
                    "previous_state": intent.aggregate_state.value
                }
            )

            # Delegate ledger write strictly to ledger service
            try:
                tx = create_financial_transaction(self.db, intent_id, request.chosen_attempt_id, actor=reviewer_id)
                return {
                    "status": "SUCCESS",
                    "decision": request.decision.value,
                    "intent_id": str(intent_id),
                    "financial_transaction_id": str(tx.id),
                    "message": "Reviewer decision accepted. Financial transaction created."
                }
            except LedgerCommitError as e:
                raise HTTPException(status_code=e.status_code, detail=e.message)

        elif request.decision == ReviewDecision.MARK_DUPLICATE:
            # Audit reviewer decision
            self.audit_service.log_event(
                entity_type="PaymentIntent",
                entity_id=intent_id,
                action="REVIEWER_MARK_DUPLICATE",
                actor=reviewer_id,
                details={
                    "reviewer_note": request.reviewer_note,
                    "previous_state": intent.aggregate_state.value
                }
            )

            self.intent_repo.update_state(intent_id, IntentState.FAILED)
            self.db.commit()

            return {
                "status": "SUCCESS",
                "decision": request.decision.value,
                "intent_id": str(intent_id),
                "message": "Reviewer marked intent as duplicate/rejected. No financial transaction committed."
            }

        raise HTTPException(status_code=400, detail="Invalid review decision")
