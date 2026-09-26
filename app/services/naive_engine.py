from decimal import Decimal
from typing import List, Dict, Any
from app.models.models import PaymentAttempt, PaymentIntent
from app.domain.enums import AttemptState

class NaiveEngine:
    @staticmethod
    def calculate_naive_exposure(attempts: List[PaymentAttempt], verity_candidate_amount: Decimal, verity_committed_amount: Decimal) -> Dict[str, Any]:
        """
        Calculates naive committable exposure by summing all SUCCESS/CONFIRMED attempts
        without correlation or duplicate detection on the exact same underlying attempt set.
        """
        naive_committable_attempts = [
            a for a in attempts
            if a.state in (AttemptState.CONFIRMED, AttemptState.GATEWAY_CONFIRMED, AttemptState.BANK_SUCCESS)
        ]

        naive_observed_amount = sum((a.amount for a in naive_committable_attempts), Decimal("0.00"))
        naive_overestimation = max(Decimal("0.00"), naive_observed_amount - verity_candidate_amount)

        return {
            "naive_observed_amount": float(naive_observed_amount),
            "verity_candidate_amount": float(verity_candidate_amount),
            "verity_committed_amount": float(verity_committed_amount),
            "naive_overestimation": float(naive_overestimation),
            "naive_attempt_count": len(naive_committable_attempts)
        }
