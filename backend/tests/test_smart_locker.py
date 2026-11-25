"""Bo kiem thu tu dong Pytest cho he thong IoT Smart Locker (TC-01 -> TC-10, ERD, Muc 3.4, Muc 7.4)."""

from datetime import timedelta
from pathlib import Path
import sys
from unittest.mock import patch

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import FACE_STORAGE_DIR
from backend.app.db import SessionLocal, init_db, utc_now
from backend.app.face import (
    FaceProcessingError,
    _get_models,
    cosine_distance,
    extract_embedding,
    face_service,
    find_best_match,
)
from backend.app.main import app
from backend.app.models import ActionLog, Locker, LockerSession, User
from backend.app.mqtt_client import mqtt_manager
from backend.seed import seed_defaults


def _make_dummy_jpeg_bytes(color=(120, 140, 160)) -> bytes:
    img = np.full((240, 240, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _unit_vec(
    seed: int, noise_to: np.ndarray | None = None, noise_scale: float = 0.0
) -> list[float]:
    rng = np.random.default_rng(seed)
    if noise_to is not None:
        vec = noise_to + rng.normal(0.0, noise_scale, size=128)
    else:
        vec = rng.normal(0.0, 1.0, size=128)
    vec = vec.astype(np.float32)
    vec /= np.linalg.norm(vec)
    return [float(x) for x in vec]


EMB_USER_A = _unit_vec(101)
EMB_USER_A_SIMILAR = _unit_vec(102, noise_to=np.array(EMB_USER_A), noise_scale=0.02)
EMB_USER_B = _unit_vec(202)
if cosine_distance(EMB_USER_A, EMB_USER_B) <= 0.45:
    EMB_USER_B = [-x for x in EMB_USER_A]


@pytest.fixture(scope="module")
def client():
    init_db()
    seed_defaults()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_db_state():
    """Dam bao DB va storage sach truoc va sau moi test case, giu nguyen seed mac dinh."""

    def _reset():
        db = SessionLocal()
        try:
            if FACE_STORAGE_DIR.exists():
                for jpg in FACE_STORAGE_DIR.glob("*.jpg"):
                    try:
                        jpg.unlink()
                    except OSError:
                        pass
            db.query(ActionLog).delete()
            db.query(LockerSession).delete()
            db.query(Locker).filter(Locker.id > 1).delete()
            db.query(User).filter(~User.username.in_(["admin", "staff"])).delete(
                synchronize_session=False
            )
            locker1 = db.query(Locker).filter(Locker.id == 1).first()
            if locker1 is not None:
                locker1.locker_number = 1
                locker1.label = "Tủ số 1"
                locker1.status = "AVAILABLE"
                locker1.door_state = "CLOSED"
                locker1.lock_state = "LOCKED"
                locker1.alert = None
                locker1.support_requested_at = None
                locker1.support_note = None
                locker1.online = True
            db.commit()
        finally:
            db.close()

    _reset()
    yield
    _reset()


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _load_sample_bytes(filename: str) -> bytes:
    path = PROJECT_ROOT / "backend" / "tests" / "samples" / filename
    assert path.exists(), f"Missing sample face image: {path}"
    return path.read_bytes()


def test_ai_pipeline_models_liveness_and_cosine_distance():
    """Kiem tra FaceRecognitionService, YuNet+SFace, checkLiveness (chong anh toi/mo) va Cosine distance."""
    detector, recognizer = _get_models()
    assert detector is not None
    assert recognizer is not None

    patch_img = np.full((112, 112, 3), 180, dtype=np.uint8)
    feat = recognizer.feature(patch_img)
    assert feat.shape == (1, 128)

    assert face_service.calculateDistance(EMB_USER_A, EMB_USER_A) < 1e-5
    assert face_service.calculateDistance(EMB_USER_A, EMB_USER_A_SIMILAR) <= 0.45
    assert face_service.calculateDistance(EMB_USER_A, EMB_USER_B) > 0.45

    matched_id, dist = face_service.findMatch(
        EMB_USER_A_SIMILAR,
        [(10, EMB_USER_A), (20, EMB_USER_B)],
    )
    assert matched_id == 10
    assert dist <= 0.45

    matched_none, _ = find_best_match(EMB_USER_B, [(10, EMB_USER_A)])
    assert matched_none is None

    # Anh rong / toi / phang mo phai bi tu choi boi check_liveness
    with pytest.raises(FaceProcessingError):
        extract_embedding(b"")

    dark_img = np.zeros((200, 200, 3), dtype=np.uint8)
    ok, buf_dark = cv2.imencode(".jpg", dark_img)
    assert ok
    with pytest.raises(FaceProcessingError):
        extract_embedding(buf_dark.tobytes())

    flat_blur_img = np.full((200, 200, 3), 128, dtype=np.uint8)
    ok, buf_flat = cv2.imencode(".jpg", flat_blur_img)
    assert ok
    with pytest.raises(FaceProcessingError):
        extract_embedding(buf_flat.tobytes())


def test_tc01_tc02_tc03_deposit_duplicate_and_retrieve_flow(client: TestClient):
    """TC-01: Gui do voi YuNet+SFace that | TC-02: Chong gui trung | TC-03: Lay do khop khuon mat."""
    img_a1 = _load_sample_bytes("person_a_1.jpg")
    img_a2 = _load_sample_bytes("person_a_2.jpg")

    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ) as mock_pub:
        resp = client.post(
            "/api/kiosk/deposit",
            files={"file": ("person_a_1.jpg", img_a1, "image/jpeg")},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["locker_id"] == 1
    assert data["locker_number"] == 1
    assert data["processing_time_ms"] > 0
    session_id = data["session_id"]
    assert data["face_image_path"] == f"backend/storage/faces/{session_id}.jpg"
    assert (PROJECT_ROOT / data["face_image_path"]).exists()
    mock_pub.assert_called_once()
    assert mock_pub.call_args.kwargs["user_type"] == "CUSTOMER"

    lockers_resp = client.get("/api/lockers")
    assert lockers_resp.status_code == 200
    assert lockers_resp.json()[0]["status"] == "OCCUPIED"

    # TC-02: Chong gui trung 1 khuon mat khi phien dang ACTIVE -> 409 Conflict
    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ):
        dup_resp = client.post(
            "/api/kiosk/deposit",
            files={"file": ("person_a_2.jpg", img_a2, "image/jpeg")},
        )
    assert dup_resp.status_code == 409

    # TC-03: Retrieve thanh cong voi anh khac cua cung nguoi A (Cosine distance <= 0.45)
    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ) as mock_pub_out:
        ret_resp = client.post(
            "/api/kiosk/retrieve",
            files={"file": ("person_a_2.jpg", img_a2, "image/jpeg")},
        )
    assert ret_resp.status_code == 200, ret_resp.text
    ret_data = ret_resp.json()
    assert ret_data["locker_id"] == 1
    assert ret_data["session_id"] == session_id
    assert ret_data["distance"] <= 0.45
    mock_pub_out.assert_called_once()

    lockers_after = client.get("/api/lockers").json()
    assert lockers_after[0]["status"] == "AVAILABLE"


def test_tc04_retrieve_wrong_face_logs_failure(client: TestClient):
    """TC-04: Tu choi lay do voi khuon mat nguoi B (HTTP 401), khong mo khoa va ghi log CHECK_OUT_FAIL."""
    img_a1 = _load_sample_bytes("person_a_1.jpg")
    img_b1 = _load_sample_bytes("person_b_1.jpg")

    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ):
        dep_resp = client.post(
            "/api/kiosk/deposit",
            files={"file": ("person_a_1.jpg", img_a1, "image/jpeg")},
        )
    assert dep_resp.status_code == 200

    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ) as mock_pub_fail:
        fail_resp = client.post(
            "/api/kiosk/retrieve",
            files={"file": ("person_b_1.jpg", img_b1, "image/jpeg")},
        )
    assert fail_resp.status_code == 401
    mock_pub_fail.assert_not_called()

    admin_token = _login(client, "admin", "admin123")
    logs_resp = client.get(
        "/api/logs",
        params={"action": "CHECK_OUT_FAIL"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert logs_resp.status_code == 200
    assert len(logs_resp.json()) == 1


def test_tc05_no_available_or_maintenance_or_offline_locker(client: TestClient):
    """TC-05: Khong cap phat tu khi tu dang MAINTENANCE, offline hoac da het tu trong."""
    img_bytes = _make_dummy_jpeg_bytes()
    staff_token = _login(client, "staff", "staff123")

    # 1. Tu dang MAINTENANCE -> HTTP 400
    r_maint = client.patch(
        "/api/lockers/1",
        json={"status": "MAINTENANCE"},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert r_maint.status_code == 200
    assert r_maint.json()["status"] == "MAINTENANCE"

    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        assert (
            client.post(
                "/api/kiosk/deposit",
                files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
            ).status_code
            == 400
        )

    # 2. Tu dang offline -> HTTP 400
    client.patch(
        "/api/lockers/1",
        json={"status": "AVAILABLE", "online": False},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        assert (
            client.post(
                "/api/kiosk/deposit",
                files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
            ).status_code
            == 400
        )

    # 3. Bat lai online, chiem Tu #1 roi nguoi B gui tiep -> HTTP 400
    client.patch(
        "/api/lockers/1",
        json={"online": True},
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        assert (
            client.post(
                "/api/kiosk/deposit",
                files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
            ).status_code
            == 200
        )

    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_B),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        resp_full = client.post(
            "/api/kiosk/deposit",
            files={"file": ("face_b.jpg", img_bytes, "image/jpeg")},
        )
    assert resp_full.status_code == 400


def test_tc07_mqtt_door_open_timeout_and_section34_payload(client: TestClient):
    """TC-07 & Muc 3.4: Xu ly DOOR_OPEN_TIMEOUT va payload Muc 3.4 ('door', 'alert': 'NONE')."""
    mqtt_manager.handle_status_payload(
        1,
        {
            "locker_id": 1,
            "online": True,
            "door": "OPEN",
            "lock_state": "LOCKED",
            "alert": "DOOR_OPEN_TIMEOUT",
        },
    )

    lockers = client.get("/api/lockers").json()
    assert lockers[0]["door_state"] == "OPEN"
    assert lockers[0]["alert"] == "DOOR_OPEN_TIMEOUT"

    admin_token = _login(client, "admin", "admin123")
    logs = client.get(
        "/api/logs",
        params={"action": "DOOR_OPEN_TIMEOUT", "locker_id": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert len(logs) == 1

    # Khi cua dong lai voi payload Muc 3.4 ('door': 'CLOSED', 'alert': 'NONE') -> alert phai = None
    mqtt_manager.handle_status_payload(
        1,
        {
            "locker_id": 1,
            "door": "CLOSED",
            "lock_state": "LOCKED",
            "alert": "NONE",
        },
    )
    lockers_closed = client.get("/api/lockers").json()
    assert lockers_closed[0]["door_state"] == "CLOSED"
    assert lockers_closed[0]["alert"] is None


def test_tc08_emergency_open_completes_session_and_frees_locker(client: TestClient):
    """TC-08: Mo tu khan cap dong phien ACTIVE, giai phong tu ve AVAILABLE va ghi log."""
    img_bytes = _make_dummy_jpeg_bytes()

    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        dep_resp = client.post(
            "/api/kiosk/deposit",
            files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
        )
    assert dep_resp.status_code == 200
    session_id = dep_resp.json()["session_id"]

    staff_token = _login(client, "staff", "staff123")
    with patch(
        "backend.app.services.locker_service.mqtt_manager.publish_command",
        return_value=True,
    ) as mock_emerg_pub:
        emerg_resp = client.post(
            "/api/lockers/1/emergency-open",
            json={"reason": "Khach hang quen mat / nho ho tro mo khan cap"},
            headers={"Authorization": f"Bearer {staff_token}"},
        )
    assert emerg_resp.status_code == 200, emerg_resp.text
    assert mock_emerg_pub.call_args.kwargs["user_type"] == "STAFF"
    emerg_data = emerg_resp.json()
    assert emerg_data["closed_session_id"] == session_id
    assert emerg_data["locker"]["status"] == "AVAILABLE"

    db = SessionLocal()
    try:
        sess = db.query(LockerSession).filter(LockerSession.id == session_id).first()
        assert sess is not None
        assert sess.status == "COMPLETED"
        assert sess.check_out_at is not None
    finally:
        db.close()

    admin_token = _login(client, "admin", "admin123")
    logs = client.get(
        "/api/logs",
        params={"action": "EMERGENCY_OPEN"},
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert len(logs) == 1


def test_tc09_mqtt_failure_rolls_back_deposit(client: TestClient):
    """TC-09: Mat ket noi MQTT khi gui do phai rollback DB (HTTP 503) va giu tu AVAILABLE."""
    img_bytes = _make_dummy_jpeg_bytes()

    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=False),
    ):
        resp = client.post(
            "/api/kiosk/deposit",
            files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
        )
    assert resp.status_code == 503

    lockers = client.get("/api/lockers").json()
    assert lockers[0]["status"] == "AVAILABLE"

    db = SessionLocal()
    try:
        assert (
            db.query(LockerSession).filter(LockerSession.status == "ACTIVE").count()
            == 0
        )
    finally:
        db.close()


def test_tc10_rbac_locker_crud_user_mgmt_and_logs_locked_for_staff(client: TestClient):
    """TC-10 & Hinh 4.1: STAFF bi chan User CRUD, Create/Delete Locker va Action Logs (HTTP 403)."""
    staff_token = _login(client, "staff", "staff123")
    admin_token = _login(client, "admin", "admin123")

    # 1. STAFF bi chan User CRUD, Action Logs va Create/Delete Locker (HTTP 403)
    assert (
        client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/logs",
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/lockers",
            json={"id": 2, "locker_number": 2, "label": "Tủ số 2"},
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/lockers/1",
            headers={"Authorization": f"Bearer {staff_token}"},
        ).status_code
        == 403
    )

    # 2. ADMIN tao, xoa Tu #2 va xem Action Logs thanh cong
    r_add_lk = client.post(
        "/api/lockers",
        json={"id": 2, "locker_number": 2, "label": "Tủ số 2"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r_add_lk.status_code == 201
    assert r_add_lk.json()["locker_number"] == 2

    r_del_lk = client.delete(
        "/api/lockers/2",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r_del_lk.status_code == 200

    assert (
        client.get(
            "/api/logs",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).status_code
        == 200
    )

    # 3. ADMIN User CRUD thanh cong
    r_create_admin = client.post(
        "/api/users",
        json={
            "username": "staff_test_2",
            "password": "password123",
            "full_name": "Nhan vien thu nghiem",
            "role": "STAFF",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r_create_admin.status_code == 201
    created_id = r_create_admin.json()["id"]

    assert (
        client.delete(
            f"/api/users/{created_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).status_code
        == 200
    )


def test_support_request_bar_auto_clear_on_timeout_and_new_user(client: TestClient):
    """Yeu cau ho tro gan voi locker hien thi va tu tat sau 5 phut hoac khi co nguoi dung moi."""
    # 1. Gui yeu cau ho tro gan voi Tu #1
    r_call = client.post(
        "/api/kiosk/call-staff",
        json={"locker_id": 1, "note": "Khach can ho tro mo tu 1"},
    )
    assert r_call.status_code == 200

    lk = client.get("/api/lockers").json()[0]
    assert lk["support_active"] is True
    assert lk["support_note"] == "Khach can ho tro mo tu 1"
    assert 0 < lk["support_remaining_seconds"] <= 300

    # 2. Gia lap qua 5 phut (>300s) -> tu dong tat
    db = SessionLocal()
    try:
        locker1 = db.query(Locker).filter(Locker.id == 1).first()
        assert locker1 is not None
        locker1.support_requested_at = utc_now() - timedelta(seconds=305)
        db.commit()
    finally:
        db.close()

    lk_expired = client.get("/api/lockers").json()[0]
    assert lk_expired["support_active"] is False
    assert lk_expired["support_note"] is None

    # 3. Gui lai yeu cau ho tro, sau do co nguoi dung moi gui do -> tu dong tat
    assert (
        client.post(
            "/api/kiosk/call-staff",
            json={"locker_id": 1, "note": "Can kiem tra lai tu 1"},
        ).status_code
        == 200
    )
    assert client.get("/api/lockers").json()[0]["support_active"] is True

    img_bytes = _make_dummy_jpeg_bytes()
    with (
        patch("backend.app.services.locker_service.face.extract_embedding", return_value=EMB_USER_A),
        patch("backend.app.services.locker_service.mqtt_manager.publish_command", return_value=True),
    ):
        assert (
            client.post(
                "/api/kiosk/deposit",
                files={"file": ("face_a.jpg", img_bytes, "image/jpeg")},
            ).status_code
            == 200
        )

    lk_new_user = client.get("/api/lockers").json()[0]
    assert lk_new_user["status"] == "OCCUPIED"
    assert lk_new_user["support_active"] is False
    assert lk_new_user["support_note"] is None
