from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.schemas.schemas import EventIngestionRequest, EventIngestionResponse, PaymentEventResponse
from app.services.ingestion_service import IngestionService
from app.repositories.repositories import PaymentEventRepository

router = APIRouter(prefix="/api/events", tags=["Events"])

@router.post("", response_model=EventIngestionResponse, status_code=200)
def ingest_event(req: EventIngestionRequest, db: Session = Depends(get_db)):
    service = IngestionService(db)
    return service.ingest_event(req)

@router.get("", response_model=List[PaymentEventResponse])
def list_events(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    repo = PaymentEventRepository(db)
    events = repo.db.query(repo.get_by_dedup_hash.__self__.model).order_by(repo.get_by_dedup_hash.__self__.model.event_created_at.desc()).limit(limit).offset(offset).all()
    return events
