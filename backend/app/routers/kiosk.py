"""Router danh cho Kiosk khach hang (gui do, lay do, goi ho tro)."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..db import get_db, utc_now
from ..models import ActionLog, Locker
from ..schemas import (
    CallStaffRequest,
    CallStaffResponse,
    KioskDepositResponse,
    KioskRetrieveResponse,
)
from ..services import locker_service

router = APIRouter(prefix="/api/kiosk", tags=["Kiosk"])


@router.post("/deposit", response_model=KioskDepositResponse)
async def kiosk_deposit(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    image_bytes = await file.read()
    return locker_service.deposit_item(db, image_bytes)


@router.post("/retrieve", response_model=KioskRetrieveResponse)
async def kiosk_retrieve(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    image_bytes = await file.read()
    return locker_service.retrieve_item(db, image_bytes)


@router.post("/call-staff", response_model=CallStaffResponse)
def kiosk_call_staff(
    payload: CallStaffRequest,
    db: Session = Depends(get_db),
):
    if payload.locker_id is not None:
        locker = db.query(Locker).filter(Locker.id == payload.locker_id).first()
        if locker is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Khong tim thay tu so {payload.locker_id}.",
            )
        locker.support_requested_at = utc_now()
        locker.support_note = payload.note.strip()

    log = ActionLog(
        locker_id=payload.locker_id,
        action="CALL_STAFF",
        details=payload.note.strip(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return CallStaffResponse(
        message="Da gui yeu cau ho tro toi nhan vien truc quay.",
        log_id=log.id,
    )

