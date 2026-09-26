from typing import List
from app.models.models import PaymentEvent
from app.schemas.schemas import TimelineItem, TimelineResponse
from uuid import UUID

class TimelineService:
    @staticmethod
    def build_timeline(intent_id: UUID, events: List[PaymentEvent]) -> TimelineResponse:
        # Sort chronologically by event_created_at (provider timestamp)
        sorted_by_created = sorted(events, key=lambda e: e.event_created_at)

        # Calculate out of order by checking if received order differs
        sorted_by_received = sorted(events, key=lambda e: e.event_received_at)
        received_rank_map = {e.id: idx for idx, e in enumerate(sorted_by_received)}

        items: List[TimelineItem] = []
        for idx, event in enumerate(sorted_by_created):
            created_idx = idx
            received_idx = received_rank_map[event.id]
            is_out_of_order = (created_idx != received_idx)

            lag_seconds = (event.event_received_at - event.event_created_at).total_seconds()

            payload_summary = {
                "amount": float(event.raw_payload.get("amount", 0)) if isinstance(event.raw_payload, dict) else 0,
                "status": event.event_type
            }

            items.append(TimelineItem(
                event_id=event.id,
                attempt_id=event.attempt_id,
                provider=event.provider,
                event_type=event.event_type,
                event_created_at=event.event_created_at,
                event_received_at=event.event_received_at,
                arrival_lag_seconds=max(0.0, lag_seconds),
                is_out_of_order=is_out_of_order,
                payload_summary=payload_summary
            ))

        return TimelineResponse(
            intent_id=intent_id,
            total_events=len(items),
            events=items
        )
