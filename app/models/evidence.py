import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "audit_evidence"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    engagement_id: Mapped[str] = mapped_column(
        ForeignKey("engagements.id"), index=True, nullable=False
    )
    upload_id: Mapped[str] = mapped_column(
        ForeignKey("source_uploads.id"), index=True, nullable=False
    )
    created_by: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="UNVERIFIED", nullable=False, index=True
    )
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
