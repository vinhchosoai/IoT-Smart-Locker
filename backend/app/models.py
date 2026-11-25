"""Mo hinh co so du lieu 4 bang chuan hoa theo ERD va Class Diagram: users, lockers, sessions, action_logs."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("ADMIN", "STAFF", name="user_role"),
        nullable=False,
        default="STAFF",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Locker(Base):
    __tablename__ = "lockers"

    # id trung voi #define LOCKER_ID tren tung ESP32
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    locker_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "AVAILABLE",
            "OCCUPIED",
            "MAINTENANCE",
            "ERROR",
            "DISABLED",
            name="locker_status",
        ),
        nullable=False,
        default="AVAILABLE",
        index=True,
    )
    door_state: Mapped[str] = mapped_column(
        Enum("CLOSED", "OPEN", name="door_state_enum"),
        nullable=False,
        default="CLOSED",
    )
    lock_state: Mapped[str] = mapped_column(
        Enum("LOCKED", "UNLOCKED", name="lock_state_enum"),
        nullable=False,
        default="LOCKED",
    )
    alert: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    support_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=None
    )
    support_note: Mapped[Optional[str]] = mapped_column(
        String(400), nullable=True, default=None
    )
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    sessions: Mapped[list["LockerSession"]] = relationship(
        "LockerSession", back_populates="locker"
    )


class LockerSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    locker_id: Mapped[int] = mapped_column(Integer, ForeignKey("lockers.id"), nullable=False, index=True)
    face_embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    face_image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "COMPLETED", "CANCELLED", name="session_status"),
        nullable=False,
        default="ACTIVE",
        index=True,
    )
    check_in_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    check_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    locker: Mapped["Locker"] = relationship("Locker", back_populates="sessions")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    locker_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("lockers.id"), nullable=True, index=True
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("sessions.id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, index=True
    )
