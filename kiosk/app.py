"""Giao dien Kiosk khach hang (Streamlit - Port 8501, khong su dung icon/emoji)."""

import os
from pathlib import Path

from dotenv import load_dotenv
import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "backend" / "tests" / "samples"
load_dotenv(PROJECT_ROOT / ".env")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

SAMPLE_OPTIONS = {
    "Không dùng ảnh mẫu": None,
    "Khách hàng A - Ảnh 1 (person_a_1.jpg)": "person_a_1.jpg",
    "Khách hàng A - Ảnh 2 cùng người (person_a_2.jpg)": "person_a_2.jpg",
    "Khách hàng B - Khác người (person_b_1.jpg)": "person_b_1.jpg",
}

st.set_page_config(
    page_title="IoT Smart Locker - Kiosk",
    layout="centered",
)

st.markdown(
    """
    <style>
    .kiosk-banner {
        padding: 1rem 1.25rem;
        border-radius: 0.5rem;
        background-color: #f0f4f8;
        border-left: 6px solid #1f77b4;
        margin-bottom: 1rem;
    }
    .locker-call {
        padding: 1.5rem;
        border-radius: 0.5rem;
        background-color: #e8f5e9;
        border: 2px solid #2e7d32;
        color: #1b5e20;
        text-align: center;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 1rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_lockers() -> list[dict]:
    try:
        resp = requests.get(f"{BACKEND_URL}/api/lockers", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except requests.RequestException:
        pass
    return []


st.title("HỆ THỐNG TỦ ĐỒ THÔNG MINH - KIOSK KHÁCH HÀNG")
st.caption("Xác thực sinh trắc học khuôn mặt (YuNet + SFace 128-D)")

lockers = fetch_lockers()
total_lockers = len(lockers)
available_lockers = [
    lk for lk in lockers if lk.get("status") == "AVAILABLE" and lk.get("online")
]

col_info1, col_info2 = st.columns(2)
with col_info1:
    st.metric("Ngăn tủ trống khả dụng", f"{len(available_lockers)} / {total_lockers}")
with col_info2:
    online_count = sum(1 for lk in lockers if lk.get("online"))
    st.metric("Thiết bị tủ đang trực tuyến", f"{online_count} / {total_lockers}")

if total_lockers == 0:
    st.warning("Không thể kết nối tới Backend API hoặc chưa có tủ nào được cấu hình.")

st.divider()

mode = st.radio(
    "Chọn thao tác bạn muốn thực hiện:",
    options=["Gửi đồ (Check-in)", "Lấy đồ (Check-out)"],
    horizontal=True,
)

st.markdown(
    '<div class="kiosk-banner">'
    "Hướng dẫn: Nhìn thẳng vào camera, đảm bảo đủ ánh sáng và bấm nút chụp ảnh bên dưới."
    "</div>",
    unsafe_allow_html=True,
)

camera_photo = st.camera_input("Chụp ảnh khuôn mặt của bạn")

uploaded_photo = None
sample_choice = "Không dùng ảnh mẫu"
with st.expander("Tải ảnh lên từ máy tính (dành cho kiểm thử khi không có webcam)"):
    uploaded_photo = st.file_uploader(
        "Chọn tệp ảnh khuôn mặt (JPG/PNG)",
        type=["jpg", "jpeg", "png"],
        key="kiosk_upload",
    )
    sample_choice = st.selectbox(
        "Hoặc chọn ảnh khuôn mặt mẫu có sẵn",
        options=list(SAMPLE_OPTIONS.keys()),
        key="kiosk_sample",
    )

selected_bytes = None
if camera_photo is not None:
    selected_bytes = camera_photo.getvalue()
elif uploaded_photo is not None:
    selected_bytes = uploaded_photo.getvalue()
elif SAMPLE_OPTIONS.get(sample_choice):
    sample_path = SAMPLES_DIR / SAMPLE_OPTIONS[sample_choice]
    if sample_path.exists():
        selected_bytes = sample_path.read_bytes()

if selected_bytes is not None:
    st.image(selected_bytes, caption="Ảnh khuôn mặt đã chọn", width=320)

button_label = (
    "Xác nhận Gửi đồ" if mode == "Gửi đồ (Check-in)" else "Xác nhận Lấy đồ"
)

if st.button(button_label, type="primary", use_container_width=True):
    if selected_bytes is None:
        st.error("Vui lòng chụp ảnh hoặc tải lên ảnh khuôn mặt trước khi xác nhận.")
    else:
        endpoint = (
            "/api/kiosk/deposit"
            if mode == "Gửi đồ (Check-in)"
            else "/api/kiosk/retrieve"
        )
        image_bytes = selected_bytes
        files = {"file": ("face.jpg", image_bytes, "image/jpeg")}
        with st.spinner("Đang xử lý nhận diện khuôn mặt và gửi lệnh tới tủ..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}{endpoint}",
                    files=files,
                    timeout=15,
                )
                data = resp.json()
                if resp.status_code == 200:
                    locker_label = data.get("locker_label", f"Tủ số {data.get('locker_id')}")
                    action_text = (
                        "Khóa điện từ đã mở. Vui lòng cất đồ và đóng kín cửa."
                        if mode == "Gửi đồ (Check-in)"
                        else "Xác thực khớp khuôn mặt. Vui lòng lấy đồ và đóng kín cửa."
                    )
                    st.markdown(
                        f'<div class="locker-call">VUI LÒNG ĐẾN {locker_label.upper()}<br/>{action_text}</div>',
                        unsafe_allow_html=True,
                    )
                    st.success(data.get("message", "Thành công!"))
                    details = {
                        "Mã phiên (Session ID)": data.get("session_id"),
                        "Ngăn tủ": locker_label,
                        "Giờ gửi": data.get("check_in_at"),
                        "Thời gian xử lý AI (ms)": data.get("processing_time_ms"),
                    }
                    if "check_out_at" in data:
                        details["Giờ lấy"] = data.get("check_out_at")
                        details["Cosine Distance"] = data.get("distance")
                    st.json(details)
                else:
                    st.error(data.get("detail", f"Yêu cầu thất bại (HTTP {resp.status_code})."))
            except requests.RequestException as exc:
                st.error(f"Lỗi kết nối tới Backend ({BACKEND_URL}): {exc}")

st.divider()
st.subheader("Hỗ trợ khách hàng")
with st.form("call_staff_form", clear_on_submit=True):
    locker_options = [f"{lk['id']} - {lk['label']}" for lk in lockers] + [
        "Không xác định"
    ]
    selected_locker_str = st.selectbox("Ngăn tủ cần hỗ trợ:", locker_options)
    support_note = st.text_input(
        "Nội dung cần hỗ trợ:",
        value="Khách hàng tại Kiosk yêu cầu nhân viên hỗ trợ mở tủ / kiểm tra.",
    )
    submit_support = st.form_submit_button("Gọi nhân viên hỗ trợ", use_container_width=True)
    if submit_support:
        locker_id_val = None
        if selected_locker_str != "Không xác định":
            locker_id_val = int(selected_locker_str.split(" - ")[0])
        try:
            resp = requests.post(
                f"{BACKEND_URL}/api/kiosk/call-staff",
                json={"locker_id": locker_id_val, "note": support_note},
                timeout=5,
            )
            if resp.status_code == 200:
                st.success("Đã gửi yêu cầu hỗ trợ tới quầy nhân viên. Vui lòng đợi trong giây lát.")
            else:
                st.error("Không thể gửi yêu cầu hỗ trợ.")
        except requests.RequestException as exc:
            st.error(f"Lỗi kết nối Backend: {exc}")

