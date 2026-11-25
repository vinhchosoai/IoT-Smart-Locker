"""Router quan ly tai khoan nhan vien (chi danh cho ADMIN - TC-10)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..db import get_db
from ..models import ActionLog, LockerSession, User
from ..schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("", response_model=List[UserRead])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.id.asc()).all()
    return [UserRead.model_validate(u) for u in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == payload.username.strip()).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ten dang nhap '{payload.username}' da ton tai.",
        )

    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        ActionLog(
            user_id=current_user.id,
            action="USER_MGMT",
            details=f"{current_user.username} tao tai khoan {user.username} (role={user.role})",
        )
    )
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay tai khoan.",
        )

    if payload.is_active is False and user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khong the tu khoa tai khoan dang dang nhap.",
        )

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.add(
        ActionLog(
            user_id=current_user.id,
            action="USER_MGMT",
            details=f"{current_user.username} cap nhat tai khoan {user.username}",
        )
    )
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khong the tu xoa tai khoan dang dang nhap.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay tai khoan.",
        )

    username = user.username
    db.query(ActionLog).filter(ActionLog.user_id == user_id).update(
        {"user_id": None}, synchronize_session=False
    )
    db.query(LockerSession).filter(LockerSession.ended_by_user_id == user_id).update(
        {"ended_by_user_id": None}, synchronize_session=False
    )
    db.add(
        ActionLog(
            user_id=current_user.id,
            action="USER_MGMT",
            details=f"{current_user.username} xoa tai khoan {username}",
        )
    )
    db.delete(user)
    db.commit()
    return {"message": f"Da xoa tai khoan {username}."}
