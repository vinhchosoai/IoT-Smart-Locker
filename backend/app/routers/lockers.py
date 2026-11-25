"""Router quan ly va giam sat trang thai ngan tu (FR-03, Hinh 4.1 Use Case, Hinh 4.2 Activity)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin, require_staff_or_admin
from ..config import SUPPORT_REQUEST_TIMEOUT_SECONDS
from ..db import get_db, utc_now
from ..models import ActionLog, Locker, LockerSession, User
from ..mqtt_client import mqtt_manager
from ..schemas import (
    ActiveSessionSummary,
    EmergencyOpenRequest,
    EmergencyOpenResponse,
    LockerCreate,
    LockerRead,
    LockerUpdate,
)
from ..services import locker_service

router = APIRouter(prefix="/api/lockers", tags=["Lockers"])


def _to_locker_read(db: Session, locker: Locker) -> LockerRead:
    active_sess = (
        db.query(LockerSession)
        .filter(
            LockerSession.locker_id == locker.id,
            LockerSession.status == "ACTIVE",
        )
        .order_by(LockerSession.id.desc())
        .first()
    )
    data = LockerRead.model_validate(locker)
    if active_sess is not None:
        data.active_session = ActiveSessionSummary.model_validate(active_sess)
    if locker.support_requested_at is not None:
        elapsed = (utc_now() - locker.support_requested_at).total_seconds()
        remaining = int(max(0, SUPPORT_REQUEST_TIMEOUT_SECONDS - elapsed))
        if remaining > 0:
            data.support_active = True
            data.support_requested_at = locker.support_requested_at
            data.support_note = locker.support_note
            data.support_remaining_seconds = remaining
    return data


@router.get("", response_model=List[LockerRead])
def list_lockers(db: Session = Depends(get_db)):
    mqtt_manager.refresh_online_states(db)
    locker_service.refresh_support_requests(db)
    lockers = db.query(Locker).order_by(Locker.locker_number.asc(), Locker.id.asc()).all()
    return [_to_locker_read(db, lk) for lk in lockers]


@router.post("", response_model=LockerRead, status_code=status.HTTP_201_CREATED)
def create_locker(
    payload: LockerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(Locker).filter(Locker.id == payload.id).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tu ID={payload.id} da ton tai trong he thong.",
        )

    locker_num = payload.locker_number if payload.locker_number is not None else payload.id
    dup_num = db.query(Locker).filter(Locker.locker_number == locker_num).first()
    if dup_num is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"So tu (locker_number={locker_num}) da ton tai.",
        )

    label = payload.label.strip() if payload.label else f"Tủ số {locker_num}"
    locker = Locker(
        id=payload.id,
        locker_number=locker_num,
        label=label,
        status=payload.status,
        door_state="CLOSED",
        lock_state="LOCKED",
        online=payload.online,
        last_seen_at=utc_now(),
    )
    db.add(locker)
    db.flush()
    db.add(
        ActionLog(
            locker_id=locker.id,
            user_id=current_user.id,
            action="LOCKER_MGMT",
            details=f"{current_user.username} tao {label} (ID={payload.id}, status={payload.status})",
        )
    )
    db.commit()
    db.refresh(locker)
    return _to_locker_read(db, locker)


@router.patch("/{locker_id}", response_model=LockerRead)
def update_locker(
    locker_id: int,
    payload: LockerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin),
):
    locker = db.query(Locker).filter(Locker.id == locker_id).first()
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay tu so {locker_id}.",
        )

    active_sess = (
        db.query(LockerSession)
        .filter(LockerSession.locker_id == locker.id, LockerSession.status == "ACTIVE")
        .first()
    )
    if (
        payload.status is not None
        and payload.status != "OCCUPIED"
        and active_sess is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tu dang co phien gui do ACTIVE. Vui long su dung Mo khan cap de ket thuc phien truoc.",
        )

    changes = []
    if payload.locker_number is not None and payload.locker_number != locker.locker_number:
        if current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chi ADMIN moi duoc doi so hieu tu (locker_number).",
            )
        dup = (
            db.query(Locker)
            .filter(Locker.locker_number == payload.locker_number, Locker.id != locker.id)
            .first()
        )
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"So tu {payload.locker_number} da duoc su dung.",
            )
        locker.locker_number = payload.locker_number
        changes.append(f"locker_number={payload.locker_number}")

    if payload.label is not None and payload.label.strip():
        locker.label = payload.label.strip()
        changes.append(f"label={locker.label}")
    if payload.status is not None and payload.status != locker.status:
        locker.status = payload.status
        changes.append(f"status={locker.status}")
    if payload.online is not None and payload.online != locker.online:
        locker.online = payload.online
        if payload.online:
            locker.last_seen_at = utc_now()
        changes.append(f"online={locker.online}")
    if payload.alert is not None:
        locker.alert = payload.alert if payload.alert.strip() else None
        changes.append(f"alert={locker.alert}")

    if changes:
        db.add(
            ActionLog(
                locker_id=locker.id,
                user_id=current_user.id,
                action="LOCKER_MGMT",
                details=f"{current_user.username} cap nhat {locker.label}: {', '.join(changes)}",
            )
        )

    db.commit()
    db.refresh(locker)
    return _to_locker_read(db, locker)


@router.delete("/{locker_id}")
def delete_locker(
    locker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    locker = db.query(Locker).filter(Locker.id == locker_id).first()
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay tu so {locker_id}.",
        )

    active_sess = (
        db.query(LockerSession)
        .filter(LockerSession.locker_id == locker.id, LockerSession.status == "ACTIVE")
        .first()
    )
    if locker.status == "OCCUPIED" or active_sess is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khong the xoa tu dang co do gui (OCCUPIED / ACTIVE session).",
        )

    label = locker.label
    old_sessions = db.query(LockerSession).filter(LockerSession.locker_id == locker.id).all()
    old_sess_ids = [s.id for s in old_sessions]
    if old_sess_ids:
        db.query(ActionLog).filter(ActionLog.session_id.in_(old_sess_ids)).update(
            {"session_id": None}, synchronize_session=False
        )
        db.query(LockerSession).filter(LockerSession.id.in_(old_sess_ids)).delete(
            synchronize_session=False
        )

    db.query(ActionLog).filter(ActionLog.locker_id == locker.id).update(
        {"locker_id": None}, synchronize_session=False
    )
    db.delete(locker)
    db.add(
        ActionLog(
            user_id=current_user.id,
            action="LOCKER_MGMT",
            details=f"{current_user.username} xoa {label} (ID={locker_id})",
        )
    )
    db.commit()
    return {"message": f"Da xoa {label} (ID={locker_id}) khoi he thong."}


@router.post("/{locker_id}/emergency-open", response_model=EmergencyOpenResponse)
def emergency_open(
    locker_id: int,
    payload: EmergencyOpenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_or_admin),
):
    result = locker_service.emergency_open_locker(
        db=db,
        locker_id=locker_id,
        current_user=current_user,
        reason=payload.reason.strip(),
    )
    return EmergencyOpenResponse(
        message=result["message"],
        locker=_to_locker_read(db, result["locker"]),
        closed_session_id=result["closed_session_id"],
    )
