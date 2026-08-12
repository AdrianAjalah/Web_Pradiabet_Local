"""SQLAlchemy models for user authentication and health questionnaires."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    profile: Mapped["UserProfileDB | None"] = relationship(
        back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )
    questionnaire_draft: Mapped["QuestionnaireDraftDB | None"] = relationship(
        back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )
    assessment_history: Mapped[list["HealthAssessmentHistoryDB"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class UserProfileDB(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    full_profile_data: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    questionnaire_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[UserDB] = relationship(back_populates="profile")


class QuestionnaireDraftDB(Base):
    __tablename__ = "questionnaire_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    draft_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_section: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    owner: Mapped[UserDB] = relationship(back_populates="questionnaire_draft")


class HealthAssessmentHistoryDB(Base):
    __tablename__ = "health_assessment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    full_profile_data: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    owner: Mapped[UserDB] = relationship(back_populates="assessment_history")
