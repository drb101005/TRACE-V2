import hashlib
import json
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


GENESIS_HASH = "0" * 64


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def append_audit_event(
    db: Session,
    *,
    engagement_id: str,
    actor_id: str,
    event_type: str,
    resource_type: str,
    resource_id: str,
    previous_status: str | None,
    new_status: str | None,
    details: dict,
):
    """Append an event to the engagement hash chain in the current transaction."""
    latest = (
        db.query(AuditEvent)
        .filter_by(engagement_id=engagement_id)
        .order_by(AuditEvent.sequence.desc())
        .first()
    )

    sequence = (latest.sequence + 1) if latest else 1
    previous_hash = latest.event_hash if latest else GENESIS_HASH
    event_id = str(uuid.uuid4())

    payload = {
        "id": event_id,
        "engagement_id": engagement_id,
        "sequence": sequence,
        "actor_id": actor_id,
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "details": details,
        "previous_hash": previous_hash,
    }
    event_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    event = AuditEvent(
        id=event_id,
        engagement_id=engagement_id,
        sequence=sequence,
        actor_id=actor_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        previous_status=previous_status,
        new_status=new_status,
        details_json=canonical_json(details),
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    db.add(event)
    db.flush()
    return event


def verify_engagement_chain(db: Session, engagement_id: str):
    events = (
        db.query(AuditEvent)
        .filter_by(engagement_id=engagement_id)
        .order_by(AuditEvent.sequence.asc())
        .all()
    )

    previous_hash = GENESIS_HASH
    expected_sequence = 1

    for event in events:
        if event.sequence != expected_sequence:
            return {
                "valid": False,
                "events_checked": expected_sequence - 1,
                "failed_event_id": event.id,
                "reason": "SEQUENCE_GAP",
            }

        if event.previous_hash != previous_hash:
            return {
                "valid": False,
                "events_checked": expected_sequence - 1,
                "failed_event_id": event.id,
                "reason": "PREVIOUS_HASH_MISMATCH",
            }

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
        expected_hash = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()

        if event.event_hash != expected_hash:
            return {
                "valid": False,
                "events_checked": expected_sequence - 1,
                "failed_event_id": event.id,
                "reason": "EVENT_HASH_MISMATCH",
            }

        previous_hash = event.event_hash
        expected_sequence += 1

    return {
        "valid": True,
        "events_checked": len(events),
        "last_hash": previous_hash,
    }
