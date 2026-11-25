"""AI Face Pipeline: FaceRecognitionService (YuNet / YOLOv5-face + SFace 128-D + Liveness + Cosine)."""

from collections import deque
from pathlib import Path
import threading
import time
from typing import Deque, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .config import (
    FACE_DETECTOR_MODEL,
    FACE_DETECTOR_TYPE,
    FACE_DISTANCE_THRESHOLD,
    FACE_MIN_LAPLACIAN_VAR,
    FACE_RECOGNIZER_MODEL,
    FACE_SCORE_THRESHOLD,
    FACE_STORAGE_DIR,
    PROJECT_ROOT,
    YOLOV5_FACE_MODEL,
)


class FaceProcessingError(ValueError):
    """Loi khi phat hien, kiem tra chat luong/liveness hoac trich xuat khuon mat."""


_model_lock = threading.Lock()
_detector = None
_yolov5_net = None
_recognizer = None
_face_processing_times_ms: Deque[float] = deque(maxlen=200)


def get_avg_face_processing_ms() -> Optional[float]:
    if not _face_processing_times_ms:
        return None
    return round(sum(_face_processing_times_ms) / len(_face_processing_times_ms), 2)


def get_active_detector_name() -> str:
    if FACE_DETECTOR_TYPE == "yolov5" and YOLOV5_FACE_MODEL.exists():
        return "YOLOv5-face + SFace-128D"
    return "YuNet + SFace-128D"


def _get_models():
    """Khoi tao va giu singleton model YuNet (hoac YOLOv5-face ONNX) va SFace."""
    global _detector, _yolov5_net, _recognizer
    with _model_lock:
        if FACE_DETECTOR_TYPE == "yolov5" and YOLOV5_FACE_MODEL.exists() and _yolov5_net is None:
            _yolov5_net = cv2.dnn.readNetFromONNX(str(YOLOV5_FACE_MODEL))

        if _detector is None:
            if not FACE_DETECTOR_MODEL.exists():
                raise FaceProcessingError(
                    f"Khong tim thay model YuNet tai: {FACE_DETECTOR_MODEL}. "
                    "Vui long chay python backend/download_models.py."
                )
            factory = getattr(cv2, "FaceDetectorYN", None)
            create_fn = (
                factory.create
                if factory is not None and hasattr(factory, "create")
                else getattr(cv2, "FaceDetectorYN_create")
            )
            _detector = create_fn(
                str(FACE_DETECTOR_MODEL),
                "",
                (320, 320),
                FACE_SCORE_THRESHOLD,
                0.3,
                5000,
            )

        if _recognizer is None:
            if not FACE_RECOGNIZER_MODEL.exists():
                raise FaceProcessingError(
                    f"Khong tim thay model SFace tai: {FACE_RECOGNIZER_MODEL}. "
                    "Vui long chay python backend/download_models.py."
                )
            factory = getattr(cv2, "FaceRecognizerSF", None)
            create_fn = (
                factory.create
                if factory is not None and hasattr(factory, "create")
                else getattr(cv2, "FaceRecognizerSF_create")
            )
            _recognizer = create_fn(str(FACE_RECOGNIZER_MODEL), "")

    return _detector, _recognizer


def check_liveness(bgr_img: np.ndarray) -> bool:
    """Kiem tra chat luong khung hinh va chong anh rong/toi/mo phang co ban (Class Diagram checkLiveness)."""
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(gray.mean())
    if mean_brightness < 15.0:
        raise FaceProcessingError("Anh qua toi hoac camera bi che khuat.")
    if mean_brightness > 250.0:
        raise FaceProcessingError("Anh bi choi sang trang, khong the xac thuc khuon mat.")

    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if laplacian_var < FACE_MIN_LAPLACIAN_VAR:
        raise FaceProcessingError(
            "Anh qua mo hoac khong dat yeu cau do net khuon mat thuc."
        )
    return True


def _detect_with_yolov5(bgr_img: np.ndarray) -> Optional[np.ndarray]:
    """Chay YOLOv5-face ONNX (neu duoc bat) va tra ve vector 15 phan tu tuong thich SFace alignCrop."""
    if _yolov5_net is None:
        return None
    h, w = bgr_img.shape[:2]
    blob = cv2.dnn.blobFromImage(bgr_img, 1.0 / 255.0, (640, 640), swapRB=True, crop=False)
    _yolov5_net.setInput(blob)
    preds = _yolov5_net.forward()
    if preds is None:
        return None
    preds = np.squeeze(preds)
    if preds.ndim != 2 or preds.shape[1] < 15:
        return None

    scores = preds[:, 4]
    mask = scores >= FACE_SCORE_THRESHOLD
    filtered = preds[mask]
    if len(filtered) == 0:
        return None

    best = filtered[int(np.argmax(filtered[:, 4] * filtered[:, 2] * filtered[:, 3]))]
    sx, sy = w / 640.0, h / 640.0
    cx, cy, bw, bh = best[0] * sx, best[1] * sy, best[2] * sx, best[3] * sy
    x1, y1 = cx - bw / 2.0, cy - bh / 2.0
    row = np.zeros(15, dtype=np.float32)
    row[0:4] = [x1, y1, bw, bh]
    for k in range(5):
        row[4 + 2 * k] = best[5 + 2 * k] * sx
        row[5 + 2 * k] = best[6 + 2 * k] * sy
    row[14] = float(best[4])
    return row


def extract_embedding_with_timing(image_bytes: bytes) -> Tuple[List[float], float]:
    """Phat hien khuon mat va trich xuat vector 128-D kem thoi gian xu ly (ms)."""
    t0 = time.perf_counter()
    if not image_bytes:
        raise FaceProcessingError("Du lieu anh rong.")

    nparr = np.frombuffer(image_bytes, np.uint8)
    bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if bgr_img is None:
        raise FaceProcessingError("Khong the giai ma dinh dang anh dau vao.")

    h, w = bgr_img.shape[:2]
    if h < 64 or w < 64:
        raise FaceProcessingError("Kich thuoc anh qua nho de nhan dien khuon mat.")

    check_liveness(bgr_img)
    detector, recognizer = _get_models()

    with _model_lock:
        best_face = None
        if FACE_DETECTOR_TYPE == "yolov5" and _yolov5_net is not None:
            best_face = _detect_with_yolov5(bgr_img)

        if best_face is None:
            detector.setInputSize((w, h))
            _, faces = detector.detect(bgr_img)
            if faces is None or len(faces) == 0:
                raise FaceProcessingError(
                    "Khong phat hien khuon mat ro rang trong khung hinh. Vui long nhin thang vao camera."
                )
            areas = faces[:, 2] * faces[:, 3] * faces[:, -1]
            best_face = faces[int(np.argmax(areas))]

        box_w, box_h = float(best_face[2]), float(best_face[3])
        if box_w < 50.0 or box_h < 50.0:
            raise FaceProcessingError(
                "Khuon mat qua nho hoac qua xa camera. Vui long lai gan hon."
            )

        aligned_face = recognizer.alignCrop(bgr_img, best_face)
        feature = recognizer.feature(aligned_face)

    vec = np.asarray(feature, dtype=np.float32).flatten()
    if vec.shape[0] != 128:
        raise FaceProcessingError(
            f"Vector dac trung khong hop le (chieu {vec.shape[0]} thay vi 128)."
        )

    norm = float(np.linalg.norm(vec))
    if norm <= 1e-8:
        raise FaceProcessingError("Khong the chuan hoa vector dac trung khuon mat.")
    vec = vec / norm

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    _face_processing_times_ms.append(elapsed_ms)
    return [float(x) for x in vec], elapsed_ms


def extract_embedding(image_bytes: bytes) -> List[float]:
    """Phat hien khuon mat lon nhat va trich xuat vector 128-D bang SFace."""
    emb, _ = extract_embedding_with_timing(image_bytes)
    return emb


def cosine_distance(emb1: Sequence[float], emb2: Sequence[float]) -> float:
    """Tinh Cosine Distance = 1 - cos(theta) nam trong khoang [0.0, 2.0]."""
    v1 = np.asarray(emb1, dtype=np.float32).flatten()
    v2 = np.asarray(emb2, dtype=np.float32).flatten()
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 <= 1e-8 or n2 <= 1e-8:
        return 1.0
    similarity = float(np.dot(v1, v2) / (n1 * n2))
    similarity = max(-1.0, min(1.0, similarity))
    return float(1.0 - similarity)


def find_best_match(
    query_emb: Sequence[float],
    candidates: Sequence[Tuple[int, Sequence[float]]],
    threshold: float = FACE_DISTANCE_THRESHOLD,
) -> Tuple[Optional[int], float]:
    """Tim ung vien co Cosine Distance nho nhat va <= threshold."""
    if not candidates:
        return None, 1.0

    best_id: Optional[int] = None
    min_dist = float("inf")
    for cand_id, cand_emb in candidates:
        dist = cosine_distance(query_emb, cand_emb)
        if dist < min_dist:
            min_dist = dist
            best_id = cand_id

    if best_id is not None and min_dist <= threshold:
        return best_id, float(min_dist)
    return None, float(min_dist)


def save_face_image(session_id: int, image_bytes: bytes) -> str:
    """Luu anh khuon mat theo session_id va tra ve duong dan tuong doi."""
    FACE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = FACE_STORAGE_DIR / f"{session_id}.jpg"

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is not None:
        cv2.imwrite(str(target_path), img)
    else:
        target_path.write_bytes(image_bytes)

    try:
        return target_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(target_path)


def remove_face_image(rel_path: Optional[str]) -> None:
    """Xoa file anh neu giao dich bi rollback."""
    if not rel_path:
        return
    p = Path(rel_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / rel_path
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


class FaceRecognitionService:
    """Lop dich vu AI tuong thich truc tiep voi Class Diagram (Hinh 4.3)."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        distance_threshold: float = FACE_DISTANCE_THRESHOLD,
    ) -> None:
        self.modelName = model_name or get_active_detector_name()
        self.distanceThreshold = distance_threshold

    def checkLiveness(self, bgr_frame: np.ndarray) -> bool:
        return check_liveness(bgr_frame)

    def extractEmbedding(self, image_bytes: bytes) -> List[float]:
        return extract_embedding(image_bytes)

    def calculateDistance(
        self, vector_a: Sequence[float], vector_b: Sequence[float]
    ) -> float:
        return cosine_distance(vector_a, vector_b)

    def findMatch(
        self,
        embedding: Sequence[float],
        active_sessions: Sequence[Tuple[int, Sequence[float]]],
    ) -> Tuple[Optional[int], float]:
        return find_best_match(embedding, active_sessions, self.distanceThreshold)


face_service = FaceRecognitionService()
