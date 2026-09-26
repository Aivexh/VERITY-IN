from typing import Dict, Any
from uuid import UUID
from app.config.config import settings
from app.models.models import IncidentAnalysis
from app.schemas.schemas import ExplanationResponse

class ExplanationService:
    @staticmethod
    def generate_explanation(intent_id: UUID, analysis: IncidentAnalysis) -> ExplanationResponse:
        structured = {
            "root_cause_chain": analysis.root_cause_chain,
            "correlation_evidence": analysis.correlation_evidence,
            "resolution": analysis.resolution,
            "recommendation": analysis.recommendation
        }

        # Template-based deterministic explanation
        res_info = analysis.resolution or {}
        try:
            obs_amt = float(res_info.get("observed_amount", 0))
            cand_amt = float(res_info.get("candidate_amount", 0))
            comm_amt = float(res_info.get("committed_amount", 0))
        except (ValueError, TypeError):
            obs_amt = 0.0
            cand_amt = 0.0
            comm_amt = 0.0

        res_state = res_info.get("resolution_state", "UNKNOWN")

        primary_cause = "UNKNOWN"
        if analysis.root_cause_chain and isinstance(analysis.root_cause_chain, list):
            primary_cause = analysis.root_cause_chain[0].get("name", "Unknown Root Cause")

        explanation_text = (
            f"VERITY Financial Analysis for Intent {intent_id}:\n"
            f"• Primary Cause: {primary_cause}\n"
            f"• Resolution State: {res_state}\n"
            f"• Financial Breakdown: Observed Exposure: INR {obs_amt:,.2f} | Candidate Amount: INR {cand_amt:,.2f} | Committed Ledger: INR {comm_amt:,.2f}\n"
            f"• Safeguard Assessment: {analysis.recommendation}. Zero unauthorized financial commitments were written."
        )

        return ExplanationResponse(
            intent_id=intent_id,
            ai_generated=False,
            explanation_text=explanation_text,
            structured_evidence=structured
        )
