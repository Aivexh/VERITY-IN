import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/verity_db"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS audit_logs, simulation_runs, incident_analyses, financial_transactions, financial_resolutions, transaction_links, payment_events, payment_attempts, payment_intents CASCADE;"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    yield
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS audit_logs, simulation_runs, incident_analyses, financial_transactions, financial_resolutions, transaction_links, payment_events, payment_attempts, payment_intents CASCADE;"))
        conn.commit()

@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean tables between tests
        with engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE audit_logs, simulation_runs, incident_analyses, financial_transactions, financial_resolutions, transaction_links, payment_events, payment_attempts, payment_intents CASCADE;"))
            conn.commit()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
