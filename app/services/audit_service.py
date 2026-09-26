from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.models import AuditLog
from app.repositories.repositories import AuditLogRepository

class AuditService:
    def __init__(self, db: Session):
        self.repo = AuditLogRepository(db)

    def log_event(
        self,
        entity_type: str,
        entity_id: str | UUID,
        action: str,
        actor: str = "SYSTEM",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        audit = AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor=actor,
            details=details or {}
        )
        return self.repo.create(audit)
