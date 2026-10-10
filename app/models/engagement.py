import uuid
from datetime import datetime, timezone
from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def utcnow():
    return datetime.now(timezone.utc)

class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="DATA_PENDING", nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class EngagementMembership(Base):
    __tablename__ = "engagement_memberships"
    __table_args__ = (UniqueConstraint("engagement_id", "user_id", name="uq_engagement_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
