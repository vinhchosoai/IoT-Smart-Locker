"""Nghiep vu cot loi: gui do, lay do, mo khan cap, goi nhan vien ho tro."""

from datetime import timedelta
import time
from typing import Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import face
from ..config import SUPPORT_REQUEST_TIMEOUT_SECONDS
from ..db import utc_now
from ..models import ActionLog, Locker, LockerSession, User
from ..mqtt_client import mqtt_manager


def refresh_support_requests(db: Session) -> None:
    """Tu dong tat yeu cau ho tro gan tren locker sau 5 phut (SUPPORT_REQUEST_TIMEOUT_SECONDS)."""
    cutoff = utc_now() - timedelta(seconds=SUPPORT_REQUEST_TIMEOUT_SECONDS)
    expired_lockers = (
        db.query(Locker)
        .filter(
            Locker.support_requested_at.isnot(None),
            Locker.support_requested_at <= cutoff,
        )
        .all()
    )
    if expired_lockers:
        for lk in expired_lockers:
            lk.support_requested_at = None
            lk.support_note = None
        db.commit()


def _extract_with_timing_compat(image_bytes: bytes) -> tuple[list[float], float]:
    """Goi extract_embedding de tuong thich ca khi unit test patch ham face.extract_embedding."""
    t0 = time.perf_counter()
    emb = face.extract_embedding(image_bytes)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return emb, elapsed_ms


def deposit_item(db: Session, image_bytes: bytes) -> Dict[str, Any]:
    """Xu ly gui do tai Kiosk (FR-01, TC-01, TC-02, TC-05, TC-09)."""
    try:
        embedding, proc_ms = _extract_with_timing_compat(image_bytes)
    except face.FaceProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # TC-02: Chong gui trung 1 khuon mat khi dang co phien ACTIVE
    active_sessions = (
        db.query(LockerSession)
        .filter(LockerSession.status == "ACTIVE")
        .all()
    )
    candidates = [(s.id, s.face_embedding) for s in active_sessions]
    matched_session_id, _ = face.find_best_match(embedding, candidates)
    if matched_session_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khuon mat nay dang co ngan tu gui do chua lay. Vui long lay do truoc khi gui moi.",
        )

    mqtt_manager.refresh_online_states(db)

    # TC-05: Chon ngan tu AVAILABLE + online = 1 voi khoa dong tranh xung dot dong thoi
    locker = (
        db.query(Locker)
        .filter(Locker.status == "AVAILABLE", Locker.online == True)  # noqa: E712
        .order_by(Locker.locker_number.asc(), Locker.id.asc())
        .with_for_update()
        .first()
    )
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hien tai da het ngan tu trong kha dung (hoac tu dang bao tri / ngoai tuyen).",
        )

    saved_image_path = None
    try:
        session = LockerSession(
            locker_id=locker.id,
            face_embedding=embedding,
            face_image_path="pending",
            status="ACTIVE",
            check_in_at=utc_now(),
        )
        db.add(session)
        db.flush()

        saved_image_path = face.save_face_image(session.id, image_bytes)
        session.face_image_path = saved_image_path

        locker.status = "OCCUPIED"
        locker.lock_state = "UNLOCKED"
        locker.alert = None
        # Tu dong tat yeu cau ho tro cu khi tu co nguoi dung moi
        locker.support_requested_at = None
        locker.support_note = None

        db.add(
            ActionLog(
                locker_id=locker.id,
                session_id=session.id,
                action="CHECK_IN",
                details=f"Khach gui do tai {locker.label} (Session #{session.id}, AI={proc_ms}ms)",
            )
        )

        # TC-09: Gui lenh MQTT mo khoa; rollback DB neu MQTT loi
        published = mqtt_manager.publish_command(
            locker_id=locker.id,
            command="OPEN",
            reason="CHECK_IN",
            session_id=session.id,
            user_type="CUSTOMER",
        )
        if not published:
            db.rollback()
            face.remove_face_image(saved_image_path)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Khong the gui lenh mo khoa toi thiet bi (MQTT mat ket noi). Giao dich da duoc hoan tac.",
            )

        db.commit()
        db.refresh(session)
        db.refresh(locker)
        return {
            "message": f"Gui do thanh cong! Vui long den {locker.label} - Khoa dien tu da mo.",
            "session_id": session.id,
            "locker_id": locker.id,
            "locker_number": locker.locker_number,
            "locker_label": locker.label,
            "check_in_at": session.check_in_at,
            "face_image_path": session.face_image_path,
            "processing_time_ms": proc_ms,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        face.remove_face_image(saved_image_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi he thong khi gui do: {exc}",
        ) from exc


def retrieve_item(db: Session, image_bytes: bytes) -> Dict[str, Any]:
    """Xu ly lay do tai Kiosk (FR-02, TC-03, TC-04, TC-09)."""
    try:
        embedding, proc_ms = _extract_with_timing_compat(image_bytes)
    except face.FaceProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    active_sessions = (
        db.query(LockerSession)
        .filter(LockerSession.status == "ACTIVE")
        .all()
    )
    candidates = [(s.id, s.face_embedding) for s in active_sessions]
    matched_session_id, min_dist = face.find_best_match(embedding, candidates)

    # TC-04: Khuon mat khong khop -> Khong mo khoa, tra HTTP 401 va ghi log CHECK_OUT_FAIL
    if matched_session_id is None:
        db.add(
            ActionLog(
                action="CHECK_OUT_FAIL",
                details=f"Nhan dien khuon mat khi lay do that bai (min_distance={min_dist:.4f}, AI={proc_ms}ms)",
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Xac thuc khuon mat that bai: Khong tim thay phien gui do phu hop.",
        )

    session = (
        db.query(LockerSession)
        .filter(LockerSession.id == matched_session_id, LockerSession.status == "ACTIVE")
        .with_for_update()
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phien gui do khong con hoat dong.",
        )

    locker = (
        db.query(Locker)
        .filter(Locker.id == session.locker_id)
        .with_for_update()
        .first()
    )
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay thong tin ngan tu.",
        )

    published = mqtt_manager.publish_command(
        locker_id=locker.id,
        command="OPEN",
        reason="CHECK_OUT",
        session_id=session.id,
        user_type="CUSTOMER",
    )
    if not published:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Khong the gui lenh mo khoa toi thiet bi (MQTT mat ket noi). Vui long thu lai.",
        )

    now = utc_now()
    session.status = "COMPLETED"
    session.check_out_at = now

    locker.status = "AVAILABLE"
    locker.lock_state = "UNLOCKED"
    locker.alert = None

    db.add(
        ActionLog(
            locker_id=locker.id,
            session_id=session.id,
            action="CHECK_OUT",
            details=(
                f"Khach lay do thanh cong tai {locker.label} "
                f"(Session #{session.id}, cosine_distance={min_dist:.4f}, AI={proc_ms}ms)"
            ),
        )
    )

    db.commit()
    db.refresh(session)
    db.refresh(locker)
    return {
        "message": f"Xac thuc thanh cong! Vui long lay do tai {locker.label}.",
        "session_id": session.id,
        "locker_id": locker.id,
        "locker_number": locker.locker_number,
        "locker_label": locker.label,
        "distance": round(min_dist, 4),
        "check_in_at": session.check_in_at,
        "check_out_at": session.check_out_at,
        "processing_time_ms": proc_ms,
    }


def emergency_open_locker(
    db: Session,
    locker_id: int,
    current_user: User,
    reason: str,
) -> Dict[str, Any]:
    """Mo tu khan cap: ket thuc phien ACTIVE (neu co), tra tu ve AVAILABLE, ghi log (FR-08, TC-08)."""
    locker = (
        db.query(Locker)
        .filter(Locker.id == locker_id)
        .with_for_update()
        .first()
    )
    if locker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay tu so {locker_id}.",
        )

    active_session = (
        db.query(LockerSession)
        .filter(
            LockerSession.locker_id == locker.id,
            LockerSession.status == "ACTIVE",
        )
        .with_for_update()
        .first()
    )

    published = mqtt_manager.publish_command(
        locker_id=locker.id,
        command="OPEN",
        reason="EMERGENCY_OPEN",
        session_id=active_session.id if active_session else None,
        user_type=current_user.role,
    )
    if not published:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Khong the gui lenh mo khan cap qua MQTT.",
        )

    closed_session_id = None
    now = utc_now()
    if active_session is not None:
        active_session.status = "COMPLETED"
        active_session.check_out_at = now
        active_session.ended_by_user_id = current_user.id
        active_session.note = f"Mo khan cap boi {current_user.username}: {reason}"
        closed_session_id = active_session.id

    locker.status = "AVAILABLE"
    locker.lock_state = "UNLOCKED"
    locker.alert = None

    db.add(
        ActionLog(
            locker_id=locker.id,
            session_id=closed_session_id,
            user_id=current_user.id,
            action="EMERGENCY_OPEN",
            details=f"Mo khan cap {locker.label} boi {current_user.username}. Ly do: {reason}",
        )
    )

    db.commit()
    db.refresh(locker)
    return {
        "message": f"Da mo khan cap {locker.label} thanh cong.",
        "locker": locker,
        "closed_session_id": closed_session_id,
    }
