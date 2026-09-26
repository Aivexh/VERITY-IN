import json
from pathlib import Path
import pytest

from app.schemas.schemas import (
    IncidentAnalysisResponse, FinancialResolutionResponse, CorrelationEvidenceResponse,
    TimelineResponse, DashboardSummaryResponse, FinancialTransactionResponse
)

def test_module2_contract_fixture_validity():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "module2_contract.json"
    assert fixture_path.exists(), "module2_contract.json fixture must exist"

    with open(fixture_path, "r") as f:
        contract_data = json.load(f)

    # Validate schema parsing against contract fixture
    analysis = IncidentAnalysisResponse.model_validate(contract_data["IncidentAnalysis"])
    assert analysis.id is not None
    assert analysis.primary_root_cause.value == "RC_NETWORK_TIMEOUT"

    resolution = FinancialResolutionResponse.model_validate(contract_data["FinancialResolution"])
    assert float(resolution.observed_amount) == 4000.0

    timeline = TimelineResponse.model_validate(contract_data["Timeline"])
    assert timeline.total_events == 4

    dashboard = DashboardSummaryResponse.model_validate(contract_data["Dashboard"])
    assert dashboard.exposure_metrics.total_observed_exposure == 4000.0

    tx = FinancialTransactionResponse.model_validate(contract_data["Transaction"])
    assert float(tx.amount) == 2000.0
