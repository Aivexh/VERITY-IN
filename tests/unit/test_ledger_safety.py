import threading
from decimal import Decimal
import pytest

from app.models.models import PaymentIntent, PaymentAttempt, FinancialTransaction
from app.domain.enums import AttemptState, IntentState
from app.services.ledger_service import create_financial_transaction, LedgerCommitError

def test_single_ledger_write_path_success(db_session):
    intent = PaymentIntent(order_id="ORD-SAFETY-1", customer_id="CUST-1", declared_amount=Decimal("500"), aggregate_state=IntentState.CONFIRMED)
    db_session.add(intent)
    db_session.flush()

    attempt = PaymentAttempt(intent_id=intent.id, provider="gw", provider_reference="r100", amount=Decimal("500"), state=AttemptState.CONFIRMED)
    db_session.add(attempt)
    db_session.commit()

    tx = create_financial_transaction(db_session, intent.id, attempt.id, actor="TEST")
    assert tx.id is not None
    assert tx.amount == Decimal("500.00")
    assert tx.intent_id == intent.id

    # Verify duplicate commit fails (Invariant I4)
    with pytest.raises(LedgerCommitError) as exc_info:
        create_financial_transaction(db_session, intent.id, attempt.id, actor="TEST")
    assert exc_info.value.status_code == 409

def test_safe_ambiguity_refuses_auto_commit_on_held_state(db_session):
    intent = PaymentIntent(order_id="ORD-HELD-1", customer_id="CUST-1", declared_amount=Decimal("500"), aggregate_state=IntentState.POTENTIAL_DUPLICATE)
    db_session.add(intent)
    db_session.flush()

    attempt = PaymentAttempt(intent_id=intent.id, provider="gw", provider_reference="r101", amount=Decimal("500"), state=AttemptState.CONFIRMED)
    db_session.add(attempt)
    db_session.commit()

    # System actor attempt to auto-commit on POTENTIAL_DUPLICATE state must be refused (Invariants I3 & I7)
    with pytest.raises(LedgerCommitError) as exc_info:
        create_financial_transaction(db_session, intent.id, attempt.id, actor="SYSTEM")
    assert exc_info.value.status_code == 409

def test_concurrency_single_ledger_commit(db_session):
    # Attempt simultaneous commits on separate threads using real PostgreSQL DB
    intent = PaymentIntent(order_id="ORD-CONC-1", customer_id="CUST-CONC", declared_amount=Decimal("2000"), aggregate_state=IntentState.CONFIRMED)
    db_session.add(intent)
    db_session.flush()

    attempt = PaymentAttempt(intent_id=intent.id, provider="gw", provider_reference="r_conc", amount=Decimal("2000"), state=AttemptState.CONFIRMED)
    db_session.add(attempt)
    db_session.commit()

    intent_id = intent.id
    attempt_id = attempt.id

    results = []

    def attempt_commit():
        from app.config.database import SessionLocal
        local_db = SessionLocal()
        try:
            tx = create_financial_transaction(local_db, intent_id, attempt_id, actor="REVIEWER_THREAD")
            results.append(("SUCCESS", tx.id))
        except LedgerCommitError as e:
            results.append(("FAILED", e.status_code))
        finally:
            local_db.close()

    t1 = threading.Thread(target=attempt_commit)
    t2 = threading.Thread(target=attempt_commit)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results if r[0] == "SUCCESS"]
    assert len(successes) == 1  # Exactly ONE transaction committed!
