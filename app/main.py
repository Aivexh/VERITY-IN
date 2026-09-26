from app.api import dashboard, events, incidents, simulations
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config.config import settings
from app.config.database import Base, engine
from app.state_machine.state_machine import InvalidStateTransitionError
from app.services.ledger_service import LedgerCommitError
from app.api import transactions

# Ensure DB tables exist on application startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.ENGINE_VERSION,
    description="VERITY Module 1 — Payment-Truth and Financial-Failure Intelligence Engine"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Exception Handlers (Section 20 Error Contract)
@app.exception_handler(InvalidStateTransitionError)
async def state_transition_exception_handler(request: Request, exc: InvalidStateTransitionError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc), "error_code": "INVALID_STATE_TRANSITION"}
    )

@app.exception_handler(LedgerCommitError)
async def ledger_commit_exception_handler(request: Request, exc: LedgerCommitError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_code": "LEDGER_COMMIT_ERROR"}
    )

# Include API Routers
app.include_router(events.router)
app.include_router(transactions.router)
app.include_router(incidents.router)
app.include_router(simulations.router)
app.include_router(dashboard.router)

@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "app": settings.APP_NAME,
        "version": settings.ENGINE_VERSION,
        "ai_enabled": settings.AI_ENABLED
    }
