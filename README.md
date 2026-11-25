# Hệ thống Tủ đồ Thông minh tích hợp Nhận diện Khuôn mặt (IoT Smart Locker)

Dự án hiện thực hóa đầy đủ báo cáo thiết kế **Hệ thống Tủ đồ Thông minh tích hợp Nhận diện Khuôn mặt (IoT Smart Locker)** gồm:
- **Backend Server (FastAPI + MySQL 8.0 + OpenCV YuNet / YOLOv5-face + SFace 128-D + paho-mqtt)**
- **Kiosk Khách hàng (Streamlit - Port 8501)**: Chụp ảnh khuôn mặt (`st.camera_input` hoặc tải ảnh / chọn ảnh mẫu kiểm thử) để gửi đồ (`FR-01`), nhận đồ (`FR-02`) và gọi nhân viên hỗ trợ.
- **Admin/Staff Dashboard (Streamlit - Port 8502)**: Đăng nhập JWT, màn hình Home gồm 2 nút lớn (`Locker System` và `Staff Management`), giám sát trạng thái tủ thời gian thực, thêm/sửa/xóa hộc tủ (`FR-03`, trạng thái `AVAILABLE` / `OCCUPIED` / `MAINTENANCE`), mở tủ khẩn cấp (`FR-08`), tra cứu nhật ký (`FR-05`), bảng chỉ tiêu đánh giá hệ thống (`Mục 7.4`) và quản lý nhân viên (`FR-04` - chỉ dành cho `ADMIN`).
- **Firmware ESP32 & Mô phỏng Wokwi (`firmware/`)**: Mô hình 1 ESP32 = 1 ngăn tủ (`#define LOCKER_ID X`), tự ngắt relay sau 5 giây bằng `millis()` (`FR-06`, `TC-06`), cảnh báo cửa mở quá 30 giây (`DOOR_OPEN_TIMEOUT`, `FR-07`, `TC-07`), gửi heartbeat mỗi 10 giây và tương thích đồng thời chuẩn JSON tại Mục 3.4 báo cáo.

---

## 1. Cấu trúc thư mục

```text
.
├── .env.example
├── .env
├── .gitignore
├── docker-compose.yml
├── start_all.ps1
├── backend/
│   ├── requirements.txt
│   ├── download_models.py
│   ├── seed.py
│   ├── models/                # Chua model YuNet / YOLOv5-face & SFace ONNX
│   ├── storage/faces/         # Luu anh khuon mat theo {session_id}.jpg
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py          # 4 bang chuan hoa: users, lockers, sessions, action_logs
│   │   ├── schemas.py
│   │   ├── auth.py            # JWT + bcrypt + RBAC (ADMIN / STAFF)
│   │   ├── face.py            # FaceRecognitionService (checkLiveness + 128-D + Cosine <= 0.45)
│   │   ├── mqtt_client.py     # Tuong thich iot_smartlocker_2026/locker/{id}/* va Muc 3.4
│   │   ├── services/locker_service.py
│   │   └── routers/{auth,kiosk,lockers,users,logs}.py
│   └── tests/
│       ├── samples/           # Anh khuon mat mau kiem thu E2E
│       └── test_smart_locker.py
├── kiosk/app.py
├── dashboard/app.py
└── firmware/
    ├── platformio.ini
    ├── wokwi.toml
    ├── diagram.json
    ├── libraries.txt
    ├── sketch.ino
    └── src/main.cpp
```

---

## 2. Hướng dẫn Cài đặt & Khởi chạy

### Bước 1: Tạo môi trường ảo Python `.venv` và cài đặt thư viện
```powershell
uv venv .venv --python python3.12
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
```

### Bước 2: Tải / chuẩn bị model AI ONNX
```powershell
.venv\Scripts\python.exe backend\download_models.py
```

### Bước 3: Khởi động hệ thống
Chạy script tự động trên Windows (tự khởi động MySQL 8.0 cổng `3306`, đồng bộ schema, seed dữ liệu mẫu và bật Backend `8000`, Kiosk `8501`, Dashboard `8502`):
```powershell
powershell -ExecutionPolicy Bypass -File .\start_all.ps1
```

### Tài khoản mặc định
- **ADMIN:** `admin` / `admin123`
- **STAFF:** `staff` / `staff123`

---

## 3. Mở rộng thêm ngăn tủ (1 ESP32 = 1 Ngăn tủ)

1. Mở `firmware/src/main.cpp` (hoặc `firmware/sketch.ino`), đổi `#define LOCKER_ID 2`.
2. Nạp firmware vào mạch ESP32 mới (hoặc mở tab mô phỏng Wokwi mới).
3. Đăng ký tủ mới trên Dashboard (`Thêm ngăn tủ mới` với quyền `ADMIN`) hoặc qua CLI:
   ```powershell
   .venv\Scripts\python.exe backend\seed.py --add-locker 2
   ```

---

## 4. Biên dịch Firmware ESP32 & Chạy kiểm thử tự động

```powershell
pio run -d firmware
.venv\Scripts\pytest.exe backend\tests\test_smart_locker.py -v
```
