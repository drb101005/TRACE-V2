import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow():
    return datetime.now(timezone.utc)

class AuditRun(Base):
    __tablename__ = "audit_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    upload_id: Mapped[str] = mapped_column(ForeignKey("source_uploads.id"), index=True, nullable=False)
    initiated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCEEDED", nullable=False)
    engine_version: Mapped[str] = mapped_column(String(40), default="trace-audit-0.1.0", nullable=False)
    rules_version: Mapped[str] = mapped_column(String(40), default="sales-register-v1", nullable=False)
    population_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class AuditFinding(Base):
    __tablename__ = "audit_findings"
    __table_args__ = (UniqueConstraint("audit_run_id", "fingerprint", name="uq_run_finding_fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_run_id: Mapped[str] = mapped_column(ForeignKey("audit_runs.id"), index=True, nullable=False)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    upload_id: Mapped[str] = mapped_column(ForeignKey("source_uploads.id"), index=True, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    amount_under_review: Mapped[str | None] = mapped_column(String(50), nullable=True)
    calculation_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
