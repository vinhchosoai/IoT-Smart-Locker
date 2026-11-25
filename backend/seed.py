"""Khoi tao CSDL MySQL, du lieu mau (admin, staff, locker #1) va ho tro --add-locker."""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.auth import hash_password
from backend.app.db import SessionLocal, init_db, utc_now
from backend.app.models import Locker, User


def seed_defaults() -> None:
    init_db()
    db = SessionLocal()
    try:
        default_users = [
            ("admin", "admin123", "Quan tri vien he thong", "ADMIN"),
            ("staff", "staff123", "Nhan vien truc quay", "STAFF"),
        ]
        for username, password, full_name, role in default_users:
            existing = db.query(User).filter(User.username == username).first()
            if existing is None:
                db.add(
                    User(
                        username=username,
                        password_hash=hash_password(password),
                        full_name=full_name,
                        role=role,
                        is_active=True,
                    )
                )
                print(f"[OK] Da tao tai khoan mau: {username} (role={role})")
            else:
                print(f"[INFO] Tai khoan {username} da ton tai.")

        locker1 = db.query(Locker).filter(Locker.id == 1).first()
        if locker1 is None:
            db.add(
                Locker(
                    id=1,
                    locker_number=1,
                    label="Tủ số 1",
                    status="AVAILABLE",
                    door_state="CLOSED",
                    lock_state="LOCKED",
                    online=True,
                    last_seen_at=utc_now(),
                )
            )
            print("[OK] Da tao tu mac dinh: Tủ số 1 (ID=1)")
        else:
            if not locker1.locker_number:
                locker1.locker_number = 1
            print("[INFO] Tủ số 1 (ID=1) da ton tai.")

        db.commit()
    finally:
        db.close()


def add_locker(locker_id: int) -> None:
    if locker_id < 1:
        raise ValueError("locker_id phai >= 1")
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(Locker).filter(Locker.id == locker_id).first()
        if existing is not None:
            print(f"[INFO] {existing.label} (ID={locker_id}) da ton tai.")
            return
        label = f"Tủ số {locker_id}"
        db.add(
            Locker(
                id=locker_id,
                locker_number=locker_id,
                label=label,
                status="AVAILABLE",
                door_state="CLOSED",
                lock_state="LOCKED",
                online=True,
                last_seen_at=utc_now(),
            )
        )
        db.commit()
        print(f"[OK] Da them ngan tu moi: {label} (ID={locker_id})")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Khoi tao du lieu he thong Smart Locker")
    parser.add_argument(
        "--add-locker",
        type=int,
        default=None,
        help="Them ngan tu moi theo LOCKER_ID (VD: --add-locker 2)",
    )
    args = parser.parse_args()

    seed_defaults()
    if args.add_locker is not None:
        add_locker(args.add_locker)


if __name__ == "__main__":
    main()
