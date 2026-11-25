"""Entrypoint ung dung FastAPI cho he thong IoT Smart Locker."""

from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db, init_db
from .mqtt_client import mqtt_manager
from .routers import auth, kiosk, lockers, logs, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mqtt_manager.start()
    yield
    mqtt_manager.stop()


app = FastAPI(
    title="IoT Smart Locker API",
    description="Backend FastAPI quan ly tu do thong minh tich hop nhan dien khuon mat va ESP32 MQTT",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kiosk.router)
app.include_router(lockers.router)
app.include_router(users.router)
app.include_router(logs.router)


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "mqtt_connected": mqtt_manager.is_connected,
    }
