"""Database models for the PrediBeat progress tracker."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DailyProgressLogDB(Base):
    """Daily progress record used by the user-facing tracker."""

    __tablename__ = "daily_progress_logs"
    __table_args__ = (UniqueConstraint("user_id", "tanggal", name="uq_daily_progress_user_tanggal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    waist_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    target_kalori: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_karbo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_protein: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_lemak: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tdee_reference: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bmr_estimated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    baseline_calories_out: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    meal_plan_kalori: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    meal_plan_karbo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    meal_plan_protein: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    meal_plan_lemak: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    selected_meal_indices: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    meal_plan_adherence_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_kalori: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_karbo: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_protein: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_lemak: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    activity_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activity_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activity_met: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    activity_calories: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    calories_out: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    deficit_calories: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_weight_change_kg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sweet_drink_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fasting_glucose: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ProgressDayDB(Base):
    """One editable/final daily progress record per user and date."""

    __tablename__ = "progress_days_v2"
    __table_args__ = (UniqueConstraint("user_id", "entry_date", name="uq_progress_days_v2_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    foods_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    activities_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    auto_finalize_on_rollover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WeeklyInsightCacheDB(Base):
    """Cached weekly AI/rule insight, regenerated at most once per day."""

    __tablename__ = "weekly_insights_v2"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_insights_v2_user_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    insight_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="rule", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="temporary", nullable=False)
    generated_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
