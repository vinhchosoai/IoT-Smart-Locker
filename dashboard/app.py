"""Dashboard Quan tri & Nhan vien (Streamlit - Port 8502, khong su dung icon/emoji)."""

import os
from pathlib import Path
import time

from dotenv import load_dotenv
import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(
    page_title="IoT Smart Locker - Dashboard",
    layout="wide",
)

if "token" not in st.session_state:
    st.session_state["token"] = None
if "user" not in st.session_state:
    st.session_state["user"] = None
if "view" not in st.session_state:
    st.session_state["view"] = "home"


def auth_headers() -> dict:
    token = st.session_state.get("token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def api_get(path: str, params: dict | None = None):
    return requests.get(
        f"{BACKEND_URL}{path}",
        headers=auth_headers(),
        params=params,
        timeout=8,
    )


def api_post(path: str, json_data: dict | None = None):
    return requests.post(
        f"{BACKEND_URL}{path}",
        headers=auth_headers(),
        json=json_data,
        timeout=10,
    )


def api_patch(path: str, json_data: dict | None = None):
    return requests.patch(
        f"{BACKEND_URL}{path}",
        headers=auth_headers(),
        json=json_data,
        timeout=8,
    )


def api_delete(path: str):
    return requests.delete(
        f"{BACKEND_URL}{path}",
        headers=auth_headers(),
        timeout=8,
    )


def logout() -> None:
    st.session_state["token"] = None
    st.session_state["user"] = None
    st.session_state["view"] = "home"
    st.rerun()


def render_login() -> None:
    st.title("HỆ THỐNG TỦ ĐỒ THÔNG MINH - ĐĂNG NHẬP QUẢN TRỊ")
    st.caption("Vui lòng đăng nhập bằng tài khoản STAFF hoặc ADMIN.")

    col_left, col_mid, col_right = st.columns([1, 2, 1])
    with col_mid:
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập", placeholder="admin hoặc staff")
            password = st.text_input("Mật khẩu", type="password")
            submitted = st.form_submit_button(
                "Đăng nhập", type="primary", use_container_width=True
            )
            if submitted:
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/api/auth/login",
                        json={"username": username.strip(), "password": password},
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state["token"] = data["access_token"]
                        st.session_state["user"] = data["user"]
                        st.session_state["view"] = "home"
                        st.rerun()
                    else:
                        detail = resp.json().get("detail", "Đăng nhập thất bại.")
                        st.error(detail)
                except requests.RequestException as exc:
                    st.error(f"Không thể kết nối Backend ({BACKEND_URL}): {exc}")


def render_topbar() -> None:
    user = st.session_state["user"]
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("HỆ THỐNG TỦ ĐỒ THÔNG MINH - DASHBOARD")
        st.caption(
            f"Người dùng: {user['full_name']} ({user['username']}) | Vai trò: {user['role']}"
        )
    with col2:
        st.write("")
        if st.button("Đăng xuất", use_container_width=True):
            logout()
    st.divider()


def render_home() -> None:
    user = st.session_state["user"]
    is_admin = user["role"] == "ADMIN"

    st.subheader("Màn hình chính - Chọn phân hệ làm việc")
    st.write("Chọn một trong hai phân hệ bên dưới để bắt đầu:")

    col1, col2 = st.columns(2, gap="large")
    with col1:
        with st.container(border=True):
            st.markdown("### Locker System")
            st.write(
                "Giám sát trạng thái các ngăn tủ thời gian thực, cập nhật trạng thái hộc tủ, mở tủ khẩn cấp và theo dõi yêu cầu hỗ trợ."
            )
            st.caption("Quyền truy cập: STAFF và ADMIN")
            if st.button(
                "Vào Locker System",
                key="btn_go_locker_system",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["view"] = "locker_system"
                st.rerun()

    with col2:
        with st.container(border=True):
            st.markdown("### Staff Management")
            st.write(
                "Tạo tài khoản nhân viên mới, khóa hoặc mở khóa tài khoản, đặt lại mật khẩu và quản lý phân quyền."
            )
            if is_admin:
                st.caption("Quyền truy cập: ADMIN (Đã mở khóa)")
                if st.button(
                    "Vào Staff Management",
                    key="btn_go_staff_mgmt",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state["view"] = "staff_management"
                    st.rerun()
            else:
                st.caption("Quyền truy cập: Chỉ dành cho ADMIN (Tài khoản STAFF bị khóa)")
                st.button(
                    "Staff Management [Chỉ dành cho ADMIN]",
                    key="btn_locked_staff_mgmt",
                    disabled=True,
                    use_container_width=True,
                )


def render_locker_system() -> None:
    user = st.session_state["user"]
    is_admin = user["role"] == "ADMIN"

    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 2])
    with nav_col1:
        if st.button("<- Home", use_container_width=True):
            st.session_state["view"] = "home"
            st.rerun()
    with nav_col2:
        st.subheader("Phân hệ: Locker System")
    with nav_col3:
        c_ref1, c_ref2 = st.columns(2)
        with c_ref1:
            if st.button("Làm mới dữ liệu", use_container_width=True):
                st.rerun()
        with c_ref2:
            auto_refresh = st.checkbox("Tự động làm mới (3 giây)", value=False)

    logs_tab_label = (
        "Nhật ký Hoạt động (Action Logs)"
        if is_admin
        else "Nhật ký Hoạt động [Chỉ dành cho ADMIN]"
    )
    tab_grid, tab_logs = st.tabs(
        [
            "Sơ đồ & Quản lý Hộc tủ",
            logs_tab_label,
        ]
    )

    with tab_grid:
        try:
            resp = api_get("/api/lockers")
            if resp.status_code == 401:
                logout()
                return
            lockers = resp.json() if resp.status_code == 200 else []
        except requests.RequestException as exc:
            st.error(f"Lỗi kết nối Backend: {exc}")
            lockers = []

        total = len(lockers)
        avail = sum(1 for lk in lockers if lk["status"] == "AVAILABLE")
        occ = sum(1 for lk in lockers if lk["status"] == "OCCUPIED")
        maint = sum(1 for lk in lockers if lk["status"] == "MAINTENANCE")
        online = sum(1 for lk in lockers if lk["online"])
        alerts = sum(1 for lk in lockers if lk.get("alert"))

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Tổng số tủ", total)
        m2.metric("Trống (AVAILABLE)", avail)
        m3.metric("Đang gửi (OCCUPIED)", occ)
        m4.metric("Bảo trì (MAINTENANCE)", maint)
        m5.metric("Trực tuyến (Online)", online)
        m6.metric("Đang cảnh báo", alerts)

        st.divider()

        if not lockers:
            st.info("Chưa có ngăn tủ nào được đăng ký.")
        else:
            cols_per_row = 3
            for idx in range(0, len(lockers), cols_per_row):
                row_cols = st.columns(cols_per_row)
                for col_idx, locker in enumerate(lockers[idx : idx + cols_per_row]):
                    with row_cols[col_idx]:
                        with st.container(border=True):
                            conn_text = "ONLINE" if locker["online"] else "OFFLINE"
                            st.markdown(
                                f"#### {locker['label']} (Số #{locker['locker_number']} | ID={locker['id']}) - [{conn_text}]"
                            )
                            st.write(f"- **Trạng thái sử dụng:** `{locker['status']}`")
                            st.write(f"- **Cửa tủ:** `{locker['door_state']}`")
                            st.write(f"- **Khóa điện từ:** `{locker['lock_state']}`")
                            st.write(
                                f"- **Last seen:** `{locker.get('last_seen_at') or 'N/A'}`"
                            )

                            if locker.get("support_active"):
                                rem_sec = int(locker.get("support_remaining_seconds") or 0)
                                mins, secs = divmod(rem_sec, 60)
                                note_txt = locker.get("support_note") or "Khách hàng yêu cầu hỗ trợ"
                                st.warning(
                                    f"YEU CAU HO TRO: {note_txt} (Tự động tắt sau {mins:02d}:{secs:02d})"
                                )

                            if locker.get("alert"):
                                st.error(f"CANH BAO: {locker['alert']}")

                            active_sess = locker.get("active_session")
                            if active_sess:
                                st.info(
                                    f"Phiên gửi đang hoạt động: #{active_sess['id']} | Bắt đầu: {active_sess['check_in_at']}"
                                )

                            with st.expander(f"Mở khẩn cấp {locker['label']}"):
                                reason = st.text_input(
                                    "Lý do mở khẩn cấp",
                                    value="Hỗ trợ khách hàng quên khuôn mặt / kẹt tủ",
                                    key=f"reason_{locker['id']}",
                                )
                                if st.button(
                                    f"Xác nhận Mở khẩn cấp #{locker['id']}",
                                    key=f"emerg_{locker['id']}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    if not reason.strip():
                                        st.warning("Vui lòng nhập lý do mở khẩn cấp.")
                                    else:
                                        try:
                                            r = api_post(
                                                f"/api/lockers/{locker['id']}/emergency-open",
                                                {"reason": reason.strip()},
                                            )
                                            if r.status_code == 200:
                                                st.success(
                                                    r.json().get(
                                                        "message", "Đã mở khẩn cấp."
                                                    )
                                                )
                                                time.sleep(0.5)
                                                st.rerun()
                                            else:
                                                st.error(
                                                    r.json().get(
                                                        "detail", "Thao tác thất bại."
                                                    )
                                                )
                                        except requests.RequestException as exc:
                                            st.error(f"Lỗi kết nối Backend: {exc}")

                            with st.expander(f"Cập nhật / Quản lý {locker['label']}"):
                                status_opts = [
                                    "AVAILABLE",
                                    "MAINTENANCE",
                                    "DISABLED",
                                    "ERROR",
                                    "OCCUPIED",
                                ]
                                cur_status_idx = (
                                    status_opts.index(locker["status"])
                                    if locker["status"] in status_opts
                                    else 0
                                )
                                upd_label = st.text_input(
                                    "Tên hiển thị",
                                    value=locker["label"],
                                    key=f"lbl_{locker['id']}",
                                )
                                upd_status = st.selectbox(
                                    "Trạng thái hộc tủ",
                                    options=status_opts,
                                    index=cur_status_idx,
                                    key=f"st_{locker['id']}",
                                )
                                upd_online = st.checkbox(
                                    "Đang trực tuyến (Online)",
                                    value=locker["online"],
                                    key=f"onl_{locker['id']}",
                                )
                                if st.button(
                                    f"Lưu cập nhật #{locker['id']}",
                                    key=f"save_lk_{locker['id']}",
                                    use_container_width=True,
                                ):
                                    try:
                                        r = api_patch(
                                            f"/api/lockers/{locker['id']}",
                                            {
                                                "label": (upd_label or "").strip(),
                                                "status": upd_status,
                                                "online": upd_online,
                                            },
                                        )
                                        if r.status_code == 200:
                                            st.success("Đã cập nhật thông tin hộc tủ.")
                                            time.sleep(0.4)
                                            st.rerun()
                                        else:
                                            st.error(
                                                r.json().get(
                                                    "detail", "Cập nhật thất bại."
                                                )
                                            )
                                    except requests.RequestException as exc:
                                        st.error(f"Lỗi kết nối Backend: {exc}")

                                if is_admin:
                                    if st.button(
                                        f"Xóa hộc tủ #{locker['id']} (ADMIN)",
                                        key=f"del_lk_{locker['id']}",
                                        disabled=(locker["status"] == "OCCUPIED"),
                                        use_container_width=True,
                                    ):
                                        try:
                                            r_del = api_delete(
                                                f"/api/lockers/{locker['id']}"
                                            )
                                            if r_del.status_code == 200:
                                                st.success(
                                                    r_del.json().get(
                                                        "message", "Đã xóa hộc tủ."
                                                    )
                                                )
                                                time.sleep(0.4)
                                                st.rerun()
                                            else:
                                                st.error(
                                                    r_del.json().get(
                                                        "detail", "Không thể xóa tủ."
                                                    )
                                                )
                                        except requests.RequestException as exc:
                                            st.error(f"Lỗi kết nối Backend: {exc}")

        with st.expander("Thêm ngăn tủ mới (ADMIN - khi mở rộng thêm mạch ESP32)"):
            if not is_admin:
                st.info("Chức năng thêm/xóa hộc tủ mới chỉ dành cho tài khoản ADMIN.")
            else:
                next_num = max((lk["id"] for lk in lockers), default=0) + 1
                with st.form("add_locker_form"):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        new_id = st.number_input(
                            "Locker ID (khớp #define LOCKER_ID)",
                            min_value=1,
                            step=1,
                            value=next_num,
                        )
                    with c2:
                        new_num = st.number_input(
                            "Số tủ (locker_number)",
                            min_value=1,
                            step=1,
                            value=next_num,
                        )
                    with c3:
                        new_label = st.text_input(
                            "Tên hiển thị", value=f"Tủ số {next_num}"
                        )
                    with c4:
                        new_online = st.checkbox("Trạng thái Online", value=True)
                    if st.form_submit_button("Thêm ngăn tủ", use_container_width=True):
                        try:
                            r = api_post(
                                "/api/lockers",
                                {
                                    "id": int(new_id),
                                    "locker_number": int(new_num),
                                    "label": new_label.strip(),
                                    "online": new_online,
                                },
                            )
                            if r.status_code == 201:
                                st.success(f"Đã thêm {new_label} (ID={new_id}).")
                                st.rerun()
                            else:
                                st.error(r.json().get("detail", "Không thể thêm tủ."))
                        except requests.RequestException as exc:
                            st.error(f"Lỗi kết nối Backend: {exc}")

    with tab_logs:
        if not is_admin:
            st.warning(
                "Tài khoản STAFF không có quyền truy cập Nhật ký Hoạt động (Action Logs). Chỉ ADMIN mới được phép xem."
            )
        else:
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                action_filter = st.selectbox(
                    "Lọc theo hành động",
                    options=[
                        "Tất cả",
                        "CHECK_IN",
                        "CHECK_OUT",
                        "CHECK_OUT_FAIL",
                        "EMERGENCY_OPEN",
                        "DOOR_OPEN_TIMEOUT",
                        "CALL_STAFF",
                        "LOCKER_MGMT",
                        "USER_MGMT",
                    ],
                )
            with f_col2:
                locker_filter = st.text_input(
                    "Lọc theo Locker ID (để trống nếu lấy tất cả)", value=""
                )
            with f_col3:
                limit_val = st.number_input(
                    "Số dòng tối đa", min_value=10, max_value=500, value=100, step=10
                )

            params: dict[str, str | int] = {"limit": int(limit_val)}
            if action_filter != "Tất cả":
                params["action"] = action_filter
            if locker_filter.strip().isdigit():
                params["locker_id"] = int(locker_filter.strip())

            try:
                r_logs = api_get("/api/logs", params=params)
                if r_logs.status_code == 200:
                    logs_data = r_logs.json()
                    if logs_data:
                        st.dataframe(logs_data, use_container_width=True)
                    else:
                        st.info("Không có bản ghi nhật ký nào phù hợp bộ lọc.")
                elif r_logs.status_code == 401:
                    logout()
                    return
                else:
                    st.error(r_logs.json().get("detail", "Không tải được nhật ký."))
            except requests.RequestException as exc:
                st.error(f"Lỗi kết nối Backend: {exc}")

    if auto_refresh:
        time.sleep(3)
        st.rerun()


def render_staff_management() -> None:
    user = st.session_state["user"]
    nav_col1, nav_col2 = st.columns([1, 4])
    with nav_col1:
        if st.button("<- Home", use_container_width=True):
            st.session_state["view"] = "home"
            st.rerun()
    with nav_col2:
        st.subheader("Phân hệ: Staff Management (Chỉ dành cho ADMIN)")

    if user["role"] != "ADMIN":
        st.error(
            "Truy cập bị từ chối: Tài khoản STAFF không có quyền quản lý nhân viên."
        )
        return

    try:
        resp = api_get("/api/users")
        if resp.status_code == 403:
            st.error("Backend từ chối truy cập (HTTP 403 Forbidden).")
            return
        if resp.status_code == 401:
            logout()
            return
        users = resp.json() if resp.status_code == 200 else []
    except requests.RequestException as exc:
        st.error(f"Lỗi kết nối Backend: {exc}")
        users = []

    st.markdown("### Danh sách tài khoản")
    if users:
        st.dataframe(users, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu tài khoản.")

    col_create, col_update = st.columns(2)
    with col_create:
        st.markdown("### Tạo tài khoản nhân viên mới")
        with st.form("create_user_form", clear_on_submit=True):
            new_username = st.text_input("Tên đăng nhập")
            new_fullname = st.text_input("Họ và tên")
            new_password = st.text_input("Mật khẩu", type="password")
            new_role = st.selectbox("Vai trò", options=["STAFF", "ADMIN"])
            if st.form_submit_button(
                "Tạo tài khoản", type="primary", use_container_width=True
            ):
                if (
                    not new_username.strip()
                    or not new_fullname.strip()
                    or len(new_password) < 4
                ):
                    st.warning(
                        "Vui lòng nhập đầy đủ thông tin (mật khẩu tối thiểu 4 ký tự)."
                    )
                else:
                    try:
                        r = api_post(
                            "/api/users",
                            {
                                "username": new_username.strip(),
                                "full_name": new_fullname.strip(),
                                "password": new_password,
                                "role": new_role,
                            },
                        )
                        if r.status_code == 201:
                            st.success(f"Đã tạo tài khoản '{new_username.strip()}'.")
                            st.rerun()
                        else:
                            st.error(
                                r.json().get("detail", "Tạo tài khoản thất bại.")
                            )
                    except requests.RequestException as exc:
                        st.error(f"Lỗi kết nối Backend: {exc}")

    with col_update:
        st.markdown("### Cập nhật / Xóa tài khoản")
        if users:
            user_choices = {
                f"{u['id']} - {u['username']} ({u['role']})": u for u in users
            }
            selected_label = st.selectbox(
                "Chọn tài khoản cần thao tác", list(user_choices.keys())
            )
            target_user = user_choices[selected_label]

            with st.form("update_user_form"):
                upd_fullname = st.text_input(
                    "Họ và tên", value=target_user["full_name"]
                )
                upd_role = st.selectbox(
                    "Vai trò",
                    options=["STAFF", "ADMIN"],
                    index=0 if target_user["role"] == "STAFF" else 1,
                )
                upd_active = st.checkbox(
                    "Đang hoạt động (is_active)", value=target_user["is_active"]
                )
                upd_password = st.text_input(
                    "Mật khẩu mới (để trống nếu giữ nguyên)", type="password"
                )
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    save_btn = st.form_submit_button(
                        "Lưu thay đổi", type="primary", use_container_width=True
                    )
                with c_btn2:
                    del_btn = st.form_submit_button(
                        "Xóa tài khoản", use_container_width=True
                    )

                if save_btn:
                    payload = {
                        "full_name": (upd_fullname or "").strip(),
                        "role": upd_role,
                        "is_active": upd_active,
                    }
                    if upd_password:
                        payload["password"] = upd_password
                    try:
                        r = api_patch(f"/api/users/{target_user['id']}", payload)
                        if r.status_code == 200:
                            st.success("Đã cập nhật tài khoản.")
                            st.rerun()
                        else:
                            st.error(r.json().get("detail", "Cập nhật thất bại."))
                    except requests.RequestException as exc:
                        st.error(f"Lỗi kết nối Backend: {exc}")

                if del_btn:
                    try:
                        r = api_delete(f"/api/users/{target_user['id']}")
                        if r.status_code == 200:
                            st.success(r.json().get("message", "Đã xóa tài khoản."))
                            st.rerun()
                        else:
                            st.error(r.json().get("detail", "Xóa thất bại."))
                    except requests.RequestException as exc:
                        st.error(f"Lỗi kết nối Backend: {exc}")


if st.session_state["token"] is None or st.session_state["user"] is None:
    render_login()
else:
    render_topbar()
    current_view = st.session_state.get("view", "home")
    if current_view == "locker_system":
        render_locker_system()
    elif current_view == "staff_management":
        render_staff_management()
    else:
        render_home()
