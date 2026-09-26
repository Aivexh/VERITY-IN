from typing import Set, Tuple
from fastapi import HTTPException
from app.domain.enums import AttemptState, IntentState

class InvalidStateTransitionError(Exception):
    def __init__(self, current_state: str, new_state: str, entity_type: str):
        self.current_state = current_state
        self.new_state = new_state
        self.entity_type = entity_type
        super().__init__(f"Invalid {entity_type} state transition from {current_state} to {new_state}")


# Allowed Attempt state transitions (flexible to ingest delayed/out-of-order/contradictory observations)
ALLOWED_ATTEMPT_TRANSITIONS: Set[Tuple[AttemptState, AttemptState]] = {
    (AttemptState.INITIATED, AttemptState.PENDING),
    (AttemptState.INITIATED, AttemptState.BANK_SUCCESS),
    (AttemptState.INITIATED, AttemptState.BANK_FAILED),
    (AttemptState.INITIATED, AttemptState.GATEWAY_CONFIRMED),
    (AttemptState.INITIATED, AttemptState.GATEWAY_FAILED),
    (AttemptState.INITIATED, AttemptState.TIMED_OUT),
    (AttemptState.INITIATED, AttemptState.CONFIRMED),
    (AttemptState.INITIATED, AttemptState.FAILED),

    (AttemptState.PENDING, AttemptState.BANK_SUCCESS),
    (AttemptState.PENDING, AttemptState.BANK_FAILED),
    (AttemptState.PENDING, AttemptState.GATEWAY_CONFIRMED),
    (AttemptState.PENDING, AttemptState.GATEWAY_FAILED),
    (AttemptState.PENDING, AttemptState.TIMED_OUT),
    (AttemptState.PENDING, AttemptState.CONFIRMED),
    (AttemptState.PENDING, AttemptState.FAILED),

    (AttemptState.BANK_SUCCESS, AttemptState.GATEWAY_CONFIRMED),
    (AttemptState.BANK_SUCCESS, AttemptState.GATEWAY_FAILED),
    (AttemptState.BANK_SUCCESS, AttemptState.TIMED_OUT),
    (AttemptState.BANK_SUCCESS, AttemptState.CONFIRMED),
    (AttemptState.BANK_SUCCESS, AttemptState.FAILED),

    (AttemptState.CONFIRMED, AttemptState.TIMED_OUT),
    (AttemptState.CONFIRMED, AttemptState.GATEWAY_FAILED),
    (AttemptState.CONFIRMED, AttemptState.FAILED),

    (AttemptState.BANK_FAILED, AttemptState.FAILED),
    (AttemptState.GATEWAY_FAILED, AttemptState.FAILED),
    (AttemptState.GATEWAY_FAILED, AttemptState.BANK_SUCCESS),

    (AttemptState.TIMED_OUT, AttemptState.GATEWAY_CONFIRMED),
    (AttemptState.TIMED_OUT, AttemptState.CONFIRMED),
    (AttemptState.TIMED_OUT, AttemptState.BANK_SUCCESS),

    (AttemptState.FAILED, AttemptState.CONFIRMED),
    (AttemptState.FAILED, AttemptState.BANK_SUCCESS),
    (AttemptState.FAILED, AttemptState.GATEWAY_CONFIRMED),
    (AttemptState.GATEWAY_CONFIRMED, AttemptState.CONFIRMED),
}

# Allowed Intent state transitions during pipeline evidence processing and manual review
ALLOWED_INTENT_TRANSITIONS: Set[Tuple[IntentState, IntentState]] = {
    (IntentState.PENDING, IntentState.CONFIRMED),
    (IntentState.PENDING, IntentState.FAILED),
    (IntentState.PENDING, IntentState.POTENTIAL_DUPLICATE),
    (IntentState.PENDING, IntentState.CONFLICTING_STATE),
    (IntentState.PENDING, IntentState.INSUFFICIENT_EVIDENCE),
    (IntentState.PENDING, IntentState.MANUAL_REVIEW),

    # Pipeline evidence progression transitions
    (IntentState.INSUFFICIENT_EVIDENCE, IntentState.CONFIRMED),
    (IntentState.INSUFFICIENT_EVIDENCE, IntentState.FAILED),
    (IntentState.INSUFFICIENT_EVIDENCE, IntentState.POTENTIAL_DUPLICATE),
    (IntentState.INSUFFICIENT_EVIDENCE, IntentState.CONFLICTING_STATE),
    (IntentState.INSUFFICIENT_EVIDENCE, IntentState.MANUAL_REVIEW),

    (IntentState.MANUAL_REVIEW, IntentState.POTENTIAL_DUPLICATE),
    (IntentState.MANUAL_REVIEW, IntentState.CONFLICTING_STATE),
    (IntentState.MANUAL_REVIEW, IntentState.INSUFFICIENT_EVIDENCE),

    (IntentState.CONFIRMED, IntentState.POTENTIAL_DUPLICATE),
    (IntentState.CONFIRMED, IntentState.CONFLICTING_STATE),
    (IntentState.CONFIRMED, IntentState.INSUFFICIENT_EVIDENCE),
    (IntentState.CONFIRMED, IntentState.MANUAL_REVIEW),

    (IntentState.POTENTIAL_DUPLICATE, IntentState.MANUAL_REVIEW),
    (IntentState.POTENTIAL_DUPLICATE, IntentState.CONFLICTING_STATE),
    (IntentState.CONFLICTING_STATE, IntentState.MANUAL_REVIEW),
    (IntentState.CONFLICTING_STATE, IntentState.POTENTIAL_DUPLICATE),

    # Reviewer-only transitions (from held duplicate / manual review to commit state)
    (IntentState.POTENTIAL_DUPLICATE, IntentState.CONFIRMED),
    (IntentState.MANUAL_REVIEW, IntentState.CONFIRMED),
    (IntentState.MANUAL_REVIEW, IntentState.FAILED),
    (IntentState.CONFLICTING_STATE, IntentState.CONFIRMED),
}

REVIEWER_ONLY_TRANSITIONS: Set[Tuple[IntentState, IntentState]] = {
    (IntentState.POTENTIAL_DUPLICATE, IntentState.CONFIRMED),
    (IntentState.MANUAL_REVIEW, IntentState.CONFIRMED),
    (IntentState.MANUAL_REVIEW, IntentState.FAILED),
    (IntentState.CONFLICTING_STATE, IntentState.CONFIRMED),
}


class StateMachine:
    @staticmethod
    def validate_attempt_transition(current: AttemptState, next_state: AttemptState) -> bool:
        if current == next_state:
            return True
        if (current, next_state) not in ALLOWED_ATTEMPT_TRANSITIONS:
            raise InvalidStateTransitionError(current.value, next_state.value, "PaymentAttempt")
        return True

    @staticmethod
    def validate_intent_transition(current: IntentState, next_state: IntentState, is_reviewer: bool = False) -> bool:
        if current == next_state:
            return True

        transition = (current, next_state)
        if transition not in ALLOWED_INTENT_TRANSITIONS:
            raise InvalidStateTransitionError(current.value, next_state.value, "PaymentIntent")

        if transition in REVIEWER_ONLY_TRANSITIONS and not is_reviewer:
            raise InvalidStateTransitionError(
                current.value,
                next_state.value,
                "PaymentIntent (Reviewer privilege required for this transition)"
            )

        return True
