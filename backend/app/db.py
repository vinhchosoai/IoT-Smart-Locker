"""Ket noi co so du lieu MySQL qua SQLAlchemy va dong bo schema."""

from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


def utc_now() -> datetime:
    """Tra ve UTC datetime khong mang tzinfo de tuong thich cot DATETIME cua MySQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_mysql_database_exists(db_url: str = DATABASE_URL) -> None:
    """Tao database MySQL neu chua ton tai."""
    url = make_url(db_url)
    if not url.drivername.startswith("mysql"):
        return
    db_name = url.database
    if not db_name:
        return
    server_url = url.set(database="")
    temp_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with temp_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        temp_engine.dispose()


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency cung cap database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sync_mysql_lockers_schema() -> None:
    """Dam bao bang lockers cu (neu co) duoc cap nhat cot locker_number va enum MAINTENANCE."""
    if not DATABASE_URL.startswith("mysql"):
        return
    inspector = inspect(engine)
    if not inspector.has_table("lockers"):
        return

    columns = {col["name"] for col in inspector.get_columns("lockers")}
    with engine.connect() as conn:
        if "locker_number" not in columns:
            conn.execute(
                text("ALTER TABLE lockers ADD COLUMN locker_number INT NULL AFTER id")
            )
            conn.execute(text("UPDATE lockers SET locker_number = id WHERE locker_number IS NULL"))
            conn.execute(
                text(
                    "ALTER TABLE lockers MODIFY COLUMN locker_number INT NOT NULL, "
                    "ADD UNIQUE INDEX ix_lockers_locker_number (locker_number)"
                )
            )
        conn.execute(
            text(
                "ALTER TABLE lockers MODIFY COLUMN status "
                "ENUM('AVAILABLE','OCCUPIED','MAINTENANCE','ERROR','DISABLED') "
                "NOT NULL DEFAULT 'AVAILABLE'"
            )
        )
        if "support_requested_at" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE lockers ADD COLUMN support_requested_at DATETIME NULL AFTER alert"
                )
            )
        if "support_note" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE lockers ADD COLUMN support_note VARCHAR(400) NULL AFTER support_requested_at"
                )
            )
        conn.commit()


def init_db() -> None:
    """Khoi tao database (neu dung MySQL), tao bang va dong bo schema."""
    ensure_mysql_database_exists(DATABASE_URL)
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _sync_mysql_lockers_schema()
