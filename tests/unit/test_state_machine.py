import pytest
from app.domain.enums import AttemptState, IntentState
from app.state_machine.state_machine import StateMachine, InvalidStateTransitionError

def test_valid_attempt_transitions():
    assert StateMachine.validate_attempt_transition(AttemptState.INITIATED, AttemptState.PENDING)
    assert StateMachine.validate_attempt_transition(AttemptState.PENDING, AttemptState.CONFIRMED)
    assert StateMachine.validate_attempt_transition(AttemptState.BANK_SUCCESS, AttemptState.GATEWAY_CONFIRMED)

def test_invalid_attempt_transitions():
    with pytest.raises(InvalidStateTransitionError):
        StateMachine.validate_attempt_transition(AttemptState.CONFIRMED, AttemptState.INITIATED)

def test_reviewer_only_intent_transition():
    # Non-reviewer should fail on POTENTIAL_DUPLICATE -> CONFIRMED
    with pytest.raises(InvalidStateTransitionError):
        StateMachine.validate_intent_transition(IntentState.POTENTIAL_DUPLICATE, IntentState.CONFIRMED, is_reviewer=False)

    # Reviewer should succeed
    assert StateMachine.validate_intent_transition(IntentState.POTENTIAL_DUPLICATE, IntentState.CONFIRMED, is_reviewer=True)
