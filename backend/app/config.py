"""Cau hinh ung dung doc tu file .env tai thu muc goc du an."""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root@127.0.0.1:3306/iot_smartlocker?charset=utf8mb4",
)
JWT_SECRET: str = os.getenv(
    "JWT_SECRET",
    "super-secret-iot-smart-locker-key-2026-minimum-32-bytes",
)
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "iot_smartlocker_2026").strip("/")
OFFLINE_TIMEOUT_SECONDS: int = int(os.getenv("OFFLINE_TIMEOUT_SECONDS", "30"))
SUPPORT_REQUEST_TIMEOUT_SECONDS: int = int(
    os.getenv("SUPPORT_REQUEST_TIMEOUT_SECONDS", "300")
)

FACE_DETECTOR_TYPE: str = os.getenv("FACE_DETECTOR_TYPE", "yunet").strip().lower()
FACE_DETECTOR_MODEL: Path = _resolve_path(
    os.getenv("FACE_DETECTOR_MODEL", "backend/models/face_detection_yunet_2023mar.onnx")
)
YOLOV5_FACE_MODEL: Path = _resolve_path(
    os.getenv("YOLOV5_FACE_MODEL", "backend/models/yolov5s-face.onnx")
)
FACE_RECOGNIZER_MODEL: Path = _resolve_path(
    os.getenv("FACE_RECOGNIZER_MODEL", "backend/models/face_recognition_sface_2021dec.onnx")
)
FACE_STORAGE_DIR: Path = _resolve_path(
    os.getenv("FACE_STORAGE_DIR", "backend/storage/faces")
)
FACE_SCORE_THRESHOLD: float = float(os.getenv("FACE_SCORE_THRESHOLD", "0.60"))
FACE_DISTANCE_THRESHOLD: float = float(os.getenv("FACE_DISTANCE_THRESHOLD", "0.45"))
FACE_MIN_LAPLACIAN_VAR: float = float(os.getenv("FACE_MIN_LAPLACIAN_VAR", "8.0"))

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
