from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.schemas.schemas import SimulationCreateRequest, SimulationRunResponse
from app.simulation.simulation_engine import SimulationEngine
from app.repositories.repositories import SimulationRunRepository

router = APIRouter(prefix="/api/simulations", tags=["Simulations"])

@router.post("", response_model=SimulationRunResponse)
def trigger_simulation(req: SimulationCreateRequest, db: Session = Depends(get_db)):
    engine = SimulationEngine(db)
    return engine.run_scenario(scenario_id=req.scenario_id, seed=req.seed)

@router.post("/{id}/run", response_model=SimulationRunResponse)
def run_simulation_by_scenario(id: str, seed: int = 42, db: Session = Depends(get_db)):
    engine = SimulationEngine(db)
    return engine.run_scenario(scenario_id=id, seed=seed)
