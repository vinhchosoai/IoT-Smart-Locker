"""Router truy xuat nhat ky hoat dong (Action Logs - chi danh cho ADMIN)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import ActionLog, User
from ..schemas import ActionLogRead

router = APIRouter(prefix="/api", tags=["Logs"])


@router.get("/logs", response_model=List[ActionLogRead])
def list_logs(
    action: Optional[str] = Query(None),
    locker_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(ActionLog)
    if action:
        query = query.filter(ActionLog.action == action.strip())
    if locker_id is not None:
        query = query.filter(ActionLog.locker_id == locker_id)

    logs = query.order_by(ActionLog.id.desc()).limit(limit).all()

    user_ids = {log.user_id for log in logs if log.user_id is not None}
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.username for u in users}

    return [
        ActionLogRead(
            id=log.id,
            locker_id=log.locker_id,
            session_id=log.session_id,
            user_id=log.user_id,
            username=user_map.get(log.user_id) if log.user_id else None,
            action=log.action,
            details=log.details,
            created_at=log.created_at,
        )
        for log in logs
    ]
