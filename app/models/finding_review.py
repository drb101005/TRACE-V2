import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class FindingReviewRecord(Base):
    __tablename__ = "audit_finding_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("audit_findings.id"), index=True, nullable=False
    )
    reviewer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    review_note: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_misstatement_amount: Mapped[float | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
