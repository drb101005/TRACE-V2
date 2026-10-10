import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class AIAnalysisRun(Base):
    __tablename__ = "ai_analysis_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    upload_id: Mapped[str] = mapped_column(
        ForeignKey("source_uploads.id"), index=True, nullable=False
    )
    engagement_id: Mapped[str] = mapped_column(
        String(36), index=True, nullable=False
    )
    executed_by: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    analysis_type: Mapped[str] = mapped_column(
        String(60), default="SALES_CUTOFF", nullable=False
    )
    rule_version: Mapped[str] = mapped_column(
        String(30), default="1.0", nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_script_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    population_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exception_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="SUCCEEDED", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
