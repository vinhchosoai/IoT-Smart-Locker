# IoT Smart Locker System with Face Recognition

An end-to-end Smart Locker system integrating facial biometric authentication, a FastAPI + MySQL backend, Streamlit web interfaces (Customer Kiosk and Admin/Staff Dashboard), and ESP32 IoT firmware with Wokwi simulation.

---

## 1. Key Features & Architecture

- **Backend Server (FastAPI + MySQL 8.0 + OpenCV + paho-mqtt):**
  - **AI Face Pipeline:** Uses **OpenCV YuNet** (or optional **YOLOv5-face ONNX**) for face detection, **checkLiveness** (brightness and Laplacian blur checks), and **OpenCV SFace** for 128-dimensional L2-normalized embeddings matched via **Cosine Distance** (`<= 0.45`).
  - **1 ESP32 = 1 Locker Model:** Each ESP32 controls a single locker identified by `#define LOCKER_ID X`, communicating over MQTT (`iot_smartlocker_2026/locker/{id}/command` and `.../status`) with 10-second heartbeats and Section 3.4 JSON compatibility.
  - **Transaction Safety:** Row-level locking (`SELECT ... FOR UPDATE`) on `AVAILABLE` and `online = 1` lockers, duplicate active-session prevention (`HTTP 409`), and automatic database rollback (`HTTP 503`) if MQTT publishing fails.
  - **Role-Based Access Control (RBAC):** JWT + bcrypt authentication with `ADMIN` and `STAFF` roles. `STAFF` accounts are restricted from `Staff Management` (`/api/users`), creating/deleting lockers, and `Action Logs` (`/api/logs`, `HTTP 403`).
- **Customer Kiosk (Streamlit - Port 8501):**
  - Supports **Deposit (Check-in)** and **Retrieve (Check-out)** via `st.camera_input` (plus image upload and sample face selection for testing without a webcam).
  - Includes a **Call Staff** support form that attaches an active support request bar directly to the selected locker on the Dashboard (auto-clears after 5 minutes or when a new user checks into that locker).
- **Admin / Staff Dashboard (Streamlit - Port 8502):**
  - JWT login leading to a two-module Home screen (**Locker System** and **Staff Management**).
  - Real-time locker grid (`AVAILABLE`, `OCCUPIED`, `MAINTENANCE`, `ONLINE`/`OFFLINE`, door/lock state, `DOOR_OPEN_TIMEOUT` alerts, per-locker support request banner), emergency open, locker CRUD, and `ADMIN`-only Action Logs & Staff CRUD.
- **ESP32 Firmware & Wokwi Simulation (`firmware/`):**
  - Non-blocking `millis()` timer logic: relay on `GPIO 26` auto-locks after 5 seconds, door switch on `GPIO 32` (`INPUT_PULLUP`) triggers buzzer (`GPIO 15`) and `DOOR_OPEN_TIMEOUT` alert after 30 seconds, plus I2C LCD 1602 (`GPIO 21`/`22`).

---

## 2. Project Structure

```text
.
├── .env.example
├── .gitignore
├── docker-compose.yml
├── pyrightconfig.json
├── start_all.ps1
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── download_models.py
│   ├── seed.py
│   ├── models/                # YuNet / YOLOv5-face & SFace ONNX models
│   ├── storage/faces/         # Stored check-in face images ({session_id}.jpg)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py          # 4 tables: users, lockers, sessions, action_logs
│   │   ├── schemas.py
│   │   ├── auth.py            # JWT + bcrypt + RBAC (ADMIN / STAFF)
│   │   ├── face.py            # FaceRecognitionService (liveness + 128-D + cosine)
│   │   ├── mqtt_client.py     # paho-mqtt background client
│   │   ├── services/locker_service.py
│   │   └── routers/{auth,kiosk,lockers,users,logs}.py
│   └── tests/
│       ├── samples/           # Sample face images for E2E testing
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

## 3. Setup & Running

### Step 1: Create `.env` and Python Virtual Environment
```powershell
Copy-Item .env.example .env
uv venv .venv --python python3.12
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
```

### Step 2: Download / Prepare AI ONNX Models
```powershell
.venv\Scripts\python.exe backend\download_models.py
```

### Step 3: Start MySQL and Launch the System
- **Option A — One-Click Windows Script** (starts local MySQL 8.0 on port `3306`, seeds sample data, and launches Backend `8000`, Kiosk `8501`, and Dashboard `8502`):
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\start_all.ps1
  ```
- **Option B — Docker + Manual Startup:**
  ```powershell
  docker compose up -d
  .venv\Scripts\python.exe backend\seed.py
  .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
  .venv\Scripts\python.exe -m streamlit run kiosk\app.py --server.port 8501 --server.headless true
  .venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.port 8502 --server.headless true
  ```

### Default Credentials & URLs
- **Customer Kiosk:** `http://127.0.0.1:8501`
- **Admin / Staff Dashboard:** `http://127.0.0.1:8502`
  - `ADMIN`: `admin` / `admin123`
  - `STAFF`: `staff` / `staff123`
- **Backend API Docs:** `http://127.0.0.1:8000/docs`

---

## 4. Scaling Up: Adding Another Locker

1. Open `firmware/src/main.cpp` (or `firmware/sketch.ino`) and set `#define LOCKER_ID 2`.
2. Update `WIFI_SSID` / `WIFI_PASSWORD` if flashing to physical ESP32 hardware, then flash (`pio run -d firmware -t upload`) or run a second Wokwi instance.
3. Register the new locker as `ADMIN` from the Dashboard (`Add new locker`) or via CLI:
   ```powershell
   .venv\Scripts\python.exe backend\seed.py --add-locker 2
   ```

---

## 5. Firmware Build & Automated Tests

```powershell
pio run -d firmware

.venv\Scripts\pytest.exe backend\tests\test_smart_locker.py -v
```
