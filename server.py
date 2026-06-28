#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import hmac
import os
import shlex
import sys
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
SECRET_FILE = Path(os.environ.get("YANDEX_IOT_ENV", WORKSPACE / ".secrets" / "yandex-iot.env"))
OPENCLAW_CONFIG_FILE = Path(os.environ.get("OPENCLAW_CONFIG", WORKSPACE.parent / "openclaw.json"))
YANDEX_INFO_URL = "https://api.iot.yandex.net/v1.0/user/info"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = shlex.split(value.strip())[0] if value.strip() else ""
    return values


def yandex_user_info() -> dict[str, Any]:
    env = load_env_file(SECRET_FILE)
    token = os.environ.get("YANDEX_IOT_ACCESS_TOKEN") or env.get("YANDEX_IOT_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(f"YANDEX_IOT_ACCESS_TOKEN is missing in {SECRET_FILE}")

    request = urllib.request.Request(YANDEX_INFO_URL, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex API HTTP {exc.code}: {body}") from exc


def telegram_bot_token() -> str | None:
    env = load_env_file(SECRET_FILE)
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    if not OPENCLAW_CONFIG_FILE.exists():
        return None
    try:
        config = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return ((config.get("channels") or {}).get("telegram") or {}).get("botToken")


def allowed_telegram_user_ids() -> set[int]:
    env = load_env_file(SECRET_FILE)
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS") or env.get("TELEGRAM_ALLOWED_USER_IDS")
    if not raw and OPENCLAW_CONFIG_FILE.exists():
        try:
            config = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
            raw = ",".join(((config.get("channels") or {}).get("telegram") or {}).get("allowFrom") or [])
        except (OSError, json.JSONDecodeError):
            raw = ""
    ids = set()
    for item in (raw or "").replace(";", ",").split(","):
        item = item.strip()
        if item.isdigit():
            ids.add(int(item))
    return ids


def verify_telegram_init_data(init_data: str) -> bool:
    if not init_data:
        return False

    params = parse_qs(init_data, strict_parsing=True)
    supplied_hash = params.pop("hash", [""])[0]
    if not supplied_hash:
        return False

    bot_token = telegram_bot_token()
    if not bot_token:
        return False

    data_check_string = "\n".join(
        f"{key}={values[0]}" for key, values in sorted(params.items()) if values
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash):
        return False

    auth_date_raw = params.get("auth_date", ["0"])[0]
    try:
        auth_date = int(auth_date_raw)
    except ValueError:
        return False
    if abs(time.time() - auth_date) > 24 * 60 * 60:
        return False

    allowed_ids = allowed_telegram_user_ids()
    if not allowed_ids:
        return False

    try:
        user = json.loads(params.get("user", ["{}"])[0])
    except json.JSONDecodeError:
        return False
    return user.get("id") in allowed_ids


def round_value(value: Any, digits: int = 1) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    return value


def climate_payload() -> dict[str, Any]:
    info = yandex_user_info()
    rooms = {room.get("id"): room.get("name") for room in info.get("rooms", [])}
    items = []

    for device in info.get("devices", []):
        props = {}
        for prop in device.get("properties", []):
            state = prop.get("state") or {}
            instance = state.get("instance")
            if instance in {"temperature", "humidity", "pressure", "battery_level"}:
                props[instance] = state.get("value")

        if "temperature" not in props and "humidity" not in props:
            continue

        items.append(
            {
                "id": device.get("id"),
                "name": device.get("name") or "Без имени",
                "room": rooms.get(device.get("room")) or "Без комнаты",
                "type": device.get("type"),
                "temperature": round_value(props.get("temperature")),
                "humidity": round_value(props.get("humidity")),
                "pressure": round_value(props.get("pressure"), 0),
                "battery": round_value(props.get("battery_level")),
            }
        )

    preferred_order = ["Спальня", "Гостиная", "Кабинет", "Кухня", "Без комнаты"]
    order = {name: index for index, name in enumerate(preferred_order)}
    items.sort(key=lambda item: (order.get(item["room"], 99), item["room"], item["name"]))

    by_room: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_room.setdefault(item["room"], []).append(item)

    return {
        "ok": True,
        "updatedAt": int(time.time()),
        "rooms": [{"name": room, "devices": devices} for room, devices in by_room.items()],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT / "static"), **kwargs)

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/api/climate":
            if not self.is_authorized():
                self.write_json({"ok": False, "error": "forbidden"}, HTTPStatus.FORBIDDEN)
                return
            self.write_json(climate_payload())
            return
        super().do_GET()

    def is_authorized(self) -> bool:
        return verify_telegram_init_data(self.headers.get("X-Telegram-Init-Data", ""))

    def write_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8095"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Yandex Climate Mini App listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
