import hashlib
import json
from types import SimpleNamespace

from app.services.audit_trail import (
    GENESIS_HASH,
    canonical_json,
    verify_engagement_chain,
)

ENGAGEMENT = "test-engagement"


def make_event(sequence, previous_hash, details):
    event = SimpleNamespace(
        id=f"event-{sequence}",
        engagement_id=ENGAGEMENT,
        sequence=sequence,
        actor_id="test-reviewer",
        event_type="FINDING_REVIEWED",
        resource_type="FINDING",
        resource_id="test-finding",
        previous_status="DRAFT",
        new_status="REJECTED",
        details_json=canonical_json(details),
        previous_hash=previous_hash,
        event_hash="",
    )

    payload = {
        "id": event.id,
        "engagement_id": event.engagement_id,
        "sequence": event.sequence,
        "actor_id": event.actor_id,
        "event_type": event.event_type,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "previous_status": event.previous_status,
        "new_status": event.new_status,
        "details": json.loads(event.details_json),
        "previous_hash": event.previous_hash,
    }

    event.event_hash = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()

    return event


class Query:
    def __init__(self, events):
        self.events = events

    def filter_by(self, **kwargs):
        self.events = [
            event for event in self.events
            if all(getattr(event, key) == value
                   for key, value in kwargs.items())
        ]
        return self

    def order_by(self, *args):
        self.events.sort(key=lambda event: event.sequence)
        return self

    def all(self):
        return self.events


class FakeDB:
    def __init__(self, events):
        self.events = events

    def query(self, model):
        return Query(list(self.events))


def valid_events():
    first = make_event(
        1, GENESIS_HASH, {"decision": "REQUEST_CHANGES"}
    )
    second = make_event(
        2, first.event_hash, {"decision": "REJECT"}
    )
    return [first, second]


def test_valid_chain_is_accepted():
    result = verify_engagement_chain(
        FakeDB(valid_events()), ENGAGEMENT
    )
    assert result["valid"] is True
    assert result["events_checked"] == 2


def test_modified_event_content_is_detected():
    events = valid_events()
    events[1].details_json = canonical_json(
        {"decision": "CONFIRM"}
    )

    result = verify_engagement_chain(FakeDB(events), ENGAGEMENT)

    assert result["valid"] is False
    assert result["reason"] == "EVENT_HASH_MISMATCH"


def test_broken_previous_hash_is_detected():
    events = valid_events()
    events[1].previous_hash = "f" * 64

    result = verify_engagement_chain(FakeDB(events), ENGAGEMENT)

    assert result["valid"] is False
    assert result["reason"] == "PREVIOUS_HASH_MISMATCH"


def test_sequence_gap_is_detected():
    events = valid_events()
    events[1].sequence = 3

    result = verify_engagement_chain(FakeDB(events), ENGAGEMENT)

    assert result["valid"] is False
    assert result["reason"] == "SEQUENCE_GAP"
