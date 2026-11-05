"""Reviews made on the event screen, back into the registry: always human, never twice."""

from collections.abc import Sequence
from typing import Any

from multiverse_contracts.events import CorporateEvent, EventRegistry, EventReview


def merge_reviews(registry: EventRegistry, rows: Sequence[dict[str, Any]]) -> EventRegistry:
    """A new registry with the reviews added; an unknown event or a repeat is refused."""
    events: dict[str, CorporateEvent] = {e.event_id: e for e in registry.events}
    for row in rows:
        event = events.get(row["event_id"])
        if event is None:
            raise ValueError(f"no event {row['event_id']}")
        review = EventReview.model_validate(
            {k: v for k, v in row.items() if k != "event_id"} | {"kind": "human"}, strict=False
        )
        if any(r.reviewer == review.reviewer for r in event.reviews):
            raise ValueError(f"{review.reviewer} already reviewed {event.event_id}")
        events[event.event_id] = event.model_copy(update={"reviews": (*event.reviews, review)})
    return registry.model_copy(update={"events": tuple(events.values())})
