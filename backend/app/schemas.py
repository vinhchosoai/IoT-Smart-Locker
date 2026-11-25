"""Pydantic schemas cho API request va response."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

LockerStatusLiteral = Literal[
    "AVAILABLE", "OCCUPIED", "MAINTENANCE", "ERROR", "DISABLED"
]


# --- Auth & Users ---
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: Literal["ADMIN", "STAFF"]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=100)
    role: Literal["ADMIN", "STAFF"] = "STAFF"


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=4, max_length=100)
    role: Optional[Literal["ADMIN", "STAFF"]] = None
    is_active: Optional[bool] = None


# --- Lockers ---
class ActiveSessionSummary(BaseModel):
    id: int
    check_in_at: datetime
    face_image_path: str

    model_config = {"from_attributes": True}


class LockerRead(BaseModel):
    id: int
    locker_number: int
    label: str
    status: LockerStatusLiteral
    door_state: Literal["CLOSED", "OPEN"]
    lock_state: Literal["LOCKED", "UNLOCKED"]
    alert: Optional[str] = None
    support_active: bool = False
    support_requested_at: Optional[datetime] = None
    support_note: Optional[str] = None
    support_remaining_seconds: Optional[int] = None
    online: bool
    last_seen_at: Optional[datetime] = None
    updated_at: datetime
    active_session: Optional[ActiveSessionSummary] = None

    model_config = {"from_attributes": True}


class LockerCreate(BaseModel):
    id: int = Field(..., ge=1, description="Trung voi LOCKER_ID nap tren ESP32")
    locker_number: Optional[int] = Field(None, ge=1)
    label: Optional[str] = Field(None, max_length=50)
    status: LockerStatusLiteral = "AVAILABLE"
    online: bool = True


class LockerUpdate(BaseModel):
    locker_number: Optional[int] = Field(None, ge=1)
    label: Optional[str] = Field(None, max_length=50)
    status: Optional[LockerStatusLiteral] = None
    online: Optional[bool] = None
    alert: Optional[str] = None


class EmergencyOpenRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


class EmergencyOpenResponse(BaseModel):
    message: str
    locker: LockerRead
    closed_session_id: Optional[int] = None


# --- Kiosk ---
class KioskDepositResponse(BaseModel):
    message: str
    session_id: int
    locker_id: int
    locker_number: int
    locker_label: str
    check_in_at: datetime
    face_image_path: str
    processing_time_ms: float


class KioskRetrieveResponse(BaseModel):
    message: str
    session_id: int
    locker_id: int
    locker_number: int
    locker_label: str
    distance: float
    check_in_at: datetime
    check_out_at: datetime
    processing_time_ms: float


class CallStaffRequest(BaseModel):
    locker_id: Optional[int] = None
    note: str = Field(default="Khach hang tai Kiosk yeu cau nhan vien ho tro", max_length=400)


class CallStaffResponse(BaseModel):
    message: str
    log_id: int


# --- Action Logs ---
class ActionLogRead(BaseModel):
    id: int
    locker_id: Optional[int] = None
    session_id: Optional[int] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    details: Optional[str] = None
    created_at: datetime
