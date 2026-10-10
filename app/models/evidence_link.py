import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class EvidenceLink(Base):
    __tablename__ = "audit_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id", "resource_type", "resource_id", "source_row_number",
            name="uq_evidence_resource_row",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(
        String(36), ForeignKey("engagements.id"), nullable=False, index=True
    )
    evidence_id = Column(
        String(36), ForeignKey("audit_evidence.id"), nullable=False, index=True
    )
    resource_type = Column(String(40), nullable=False, default="AI_ANALYSIS_RUN")
    resource_id = Column(String(36), nullable=False, index=True)
    source_row_number = Column(Integer, nullable=True)
    linked_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
