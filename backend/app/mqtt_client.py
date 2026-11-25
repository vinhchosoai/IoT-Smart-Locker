"""Quan ly ket noi MQTT (paho-mqtt) giao tiep voi ESP32 (tuong thich Muc 3.4 va 1 ESP32 = 1 Locker)."""

from datetime import datetime, timedelta, timezone
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from sqlalchemy.orm import Session

from .config import (
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_TOPIC_PREFIX,
    OFFLINE_TIMEOUT_SECONDS,
)
from .db import SessionLocal, utc_now
from .models import ActionLog, Locker

logger = logging.getLogger(__name__)


class MQTTManager:
    """Client MQTT chay nen dong bo trang thai tu va gui lenh mo khoa."""

    def __init__(self) -> None:
        self._client: Optional[mqtt.Client] = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._started = False
        self._heartbeat_lockers: set[int] = set()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            client_id = f"smartlocker-backend-{int(time.time())}"
            self._client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message
            try:
                self._client.connect_async(
                    MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60
                )
                self._client.loop_start()
                self._started = True
            except Exception as exc:
                logger.warning("Khong the khoi tao ket noi MQTT: %s", exc)

    def stop(self) -> None:
        with self._lock:
            if not self._started or self._client is None:
                return
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            finally:
                self._connected.clear()
                self._started = False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0:
            self._connected.set()
            wildcard_topic = f"{MQTT_TOPIC_PREFIX}/locker/+/status"
            legacy_topic = f"{MQTT_TOPIC_PREFIX}/status"
            client.subscribe(wildcard_topic, qos=1)
            client.subscribe(legacy_topic, qos=1)
            logger.info("Da ket noi MQTT Broker va subscribe %s, %s", wildcard_topic, legacy_topic)
        else:
            self._connected.clear()
            logger.warning("Ket noi MQTT that bai voi ma loi: %s", reason_code)

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
        self._connected.clear()
        logger.warning("Mat ket noi MQTT Broker (code=%s)", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:
            logger.warning("Payload MQTT khong phai JSON hop le (%s): %s", msg.topic, exc)
            return

        locker_id = self._extract_locker_id(msg.topic, payload)
        if locker_id is None:
            return
        self.handle_status_payload(locker_id, payload)

    @staticmethod
    def _extract_locker_id(topic: str, payload: Dict[str, Any]) -> Optional[int]:
        match = re.search(r"/locker/(\d+)/status$", topic)
        if match:
            return int(match.group(1))
        raw_id = payload.get("locker_id")
        if raw_id is not None:
            try:
                return int(raw_id)
            except (TypeError, ValueError):
                return None
        return None

    def handle_status_payload(
        self,
        locker_id: int,
        payload: Dict[str, Any],
        db_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        """Cap nhat trang thai cua/khoa/canh bao va nhat ky DOOR_OPEN_TIMEOUT (TC-07 & Muc 3.4)."""
        db = db_factory()
        try:
            locker = db.query(Locker).filter(Locker.id == locker_id).first()
            if locker is None:
                logger.info("Bo qua status cho locker_id=%s (chua dang ky trong DB)", locker_id)
                return

            prev_alert = locker.alert
            now = utc_now()

            if payload.get("online") is False:
                locker.online = False
                locker.updated_at = now
                db.commit()
                return

            self._heartbeat_lockers.add(locker_id)
            locker.online = True
            locker.last_seen_at = now

            # Ho tro ca 'door_state' (MVP) va 'door' (Muc 3.4 bao cao)
            door_state = payload.get("door_state") or payload.get("door")
            if door_state in ("OPEN", "CLOSED"):
                locker.door_state = door_state

            lock_state = payload.get("lock_state")
            if lock_state in ("LOCKED", "UNLOCKED"):
                locker.lock_state = lock_state

            # Chuan hoa 'NONE' / 'NULL' / '' thanh None de khong bao canh bao gia
            raw_alert = payload.get("alert")
            alert_val = str(raw_alert).strip() if raw_alert is not None else None
            if alert_val is not None and alert_val.upper() in ("", "NONE", "NULL"):
                alert_val = None
            locker.alert = alert_val

            if alert_val == "DOOR_OPEN_TIMEOUT" and prev_alert != "DOOR_OPEN_TIMEOUT":
                db.add(
                    ActionLog(
                        locker_id=locker.id,
                        action="DOOR_OPEN_TIMEOUT",
                        details=f"Canh bao {locker.label} mo cua qua 30 giay khong dong",
                    )
                )

            locker.updated_at = now
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Loi xu ly MQTT status locker_id=%s: %s", locker_id, exc)
        finally:
            db.close()

    def refresh_online_states(self, db: Session, enforce_all: bool = False) -> None:
        """Danh dau offline neu tu da gui heartbeat truoc do nhung qua han OFFLINE_TIMEOUT_SECONDS."""
        cutoff = utc_now() - timedelta(seconds=OFFLINE_TIMEOUT_SECONDS)
        target_ids = list(self._heartbeat_lockers)
        query = db.query(Locker).filter(Locker.online == True)  # noqa: E712
        if not enforce_all:
            if not target_ids:
                return
            query = query.filter(Locker.id.in_(target_ids))

        expired = query.filter(
            Locker.last_seen_at.isnot(None),
            Locker.last_seen_at < cutoff,
        ).all()
        if expired:
            for locker in expired:
                locker.online = False
            db.commit()

    def publish_command(
        self,
        locker_id: int,
        command: str = "OPEN",
        reason: str = "CHECK_IN",
        session_id: Optional[int] = None,
        user_type: str = "CUSTOMER",
    ) -> bool:
        """Gui lenh mo khoa xuong ESP32 (day du truong theo Muc 3.4 bao cao va 1-ESP32-per-locker)."""
        if self._client is None:
            return False
        if not self._connected.is_set():
            if not self._started:
                return False
            if not self._connected.wait(timeout=2.5):
                return False

        topic = f"{MQTT_TOPIC_PREFIX}/locker/{locker_id}/command"
        iso_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {
            "locker_id": locker_id,
            "action": command,
            "command": command,
            "user_type": user_type,
            "reason": reason,
            "session_id": session_id,
            "timestamp": iso_ts,
        }
        try:
            info = self._client.publish(topic, json.dumps(payload), qos=1)
            info.wait_for_publish(timeout=3.0)
            return info.is_published()
        except Exception as exc:
            logger.error("Gui lenh MQTT that bai (%s): %s", topic, exc)
            return False


mqtt_manager = MQTTManager()
