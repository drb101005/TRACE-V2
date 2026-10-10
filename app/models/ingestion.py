import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow():
    return datetime.now(timezone.utc)

class SourceUpload(Base):
    __tablename__ = "source_uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_type: Mapped[str] = mapped_column(String(60), default="sales_register", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="UPLOADED", nullable=False, index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    column_mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    upload_id: Mapped[str] = mapped_column(ForeignKey("source_uploads.id"), index=True, nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(60), default="queued", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="Job queued", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("upload_id", "source_row_number", name="uq_upload_source_row"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id: Mapped[str] = mapped_column(ForeignKey("source_uploads.id"), index=True, nullable=False)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
