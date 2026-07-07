import base64
import html
import getpass
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from solar_rs485_monitor.sinks.mariadb import (
    get_mariadb_config,
    require_identifier as require_mariadb_identifier,
    validate_mariadb_config,
)
from solar_rs485_monitor.sinks.sqlite import (
    ensure_sqlite_table,
    get_sqlite_config,
    require_identifier as require_sqlite_identifier,
)
from solar_rs485_monitor.version import get_version


CONFIG_FILENAME = "solar-rs485-monitor.conf"
DEFAULT_DASHBOARD_TITLE = "Solar RS485 Monitor"
DEFAULT_DASHBOARD_LANGUAGE = "ko"
DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS = 60
DEFAULT_DASHBOARD_MAX_POINTS = 10000
DEFAULT_DASHBOARD_TIME_AXIS_MODE = "fixed"
DEFAULT_DASHBOARD_RANGE = "Last 2 days"
DEFAULT_DASHBOARD_MONTHLY_GENERATION_MONTHS = 12
DEFAULT_DASHBOARD_YEARLY_GENERATION_YEARS = 5
DASHBOARD_AUTH_HASH_ALGORITHM = "pbkdf2_sha256"
DASHBOARD_AUTH_HASH_ITERATIONS = 260000
DASHBOARD_AUTH_SESSION_KEY = "solar_rs485_monitor_dashboard_auth_user"
DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY = "solar_rs485_monitor_dashboard_auth_expires_at"
DASHBOARD_AUTH_SESSION_EXPIRED_KEY = "solar_rs485_monitor_dashboard_auth_expired"
DASHBOARD_AUTH_COOKIE_NAME = "solar_rs485_monitor_dashboard_auth"
DASHBOARD_AUTH_PROOF_COOKIE_NAME = "solar_rs485_monitor_dashboard_auth_proof"
DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS = 86400
DEFAULT_DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS = "admin"
DASHBOARD_AUTH_PERSISTENT_COOKIE_MAX_AGE_SECONDS = 10 * 365 * 24 * 60 * 60
DASHBOARD_AUTH_CHALLENGE_TTL_SECONDS = 120
CRYPTO_JS_ASSET_PATH = Path(__file__).resolve().parent / "assets" / "crypto-js-4.2.0.min.js"

METRICS = {
    "input_dc_voltage_v": "DC input voltage (V)",
    "input_dc_current_a": "DC input current (A)",
    "input_dc_power_w": "DC input power (W)",
    "output_ac_voltage_v": "AC output voltage (V)",
    "output_ac_current_a": "AC output current (A)",
    "output_ac_power_w": "AC output power (W)",
    "output_ac_power_factor_pct": "AC output power factor (%)",
    "output_ac_frequency_hz": "AC output frequency (Hz)",
    "total_generation_kwh": "Total generation (kWh)",
    "fault_code": "Fault code",
}

GENERATION_SNAPSHOT_METRICS = {
    "daily_generation_kwh": "Daily generation (kWh)",
    "monthly_generation_kwh": "Monthly generation (kWh)",
    "yearly_generation_kwh": "Yearly generation (kWh)",
}

METRIC_LABELS = {
    "ko": {
        "input_dc_voltage_v": "DC 입력 전압 (V)",
        "input_dc_current_a": "DC 입력 전류 (A)",
        "input_dc_power_w": "DC 입력 전력 (W)",
        "output_ac_voltage_v": "AC 출력 전압 (V)",
        "output_ac_current_a": "AC 출력 전류 (A)",
        "output_ac_power_w": "AC 출력 전력 (W)",
        "output_ac_power_factor_pct": "AC 출력 역률 (%)",
        "output_ac_frequency_hz": "AC 출력 주파수 (Hz)",
        "total_generation_kwh": "누적 발전량 (kWh)",
        "daily_generation_kwh": "일일 발전량 (kWh)",
        "monthly_generation_kwh": "월간 발전량 (kWh)",
        "yearly_generation_kwh": "연간 발전량 (kWh)",
        "fault_code": "점검 코드",
    },
    "en": {
        **METRICS,
        **GENERATION_SNAPSHOT_METRICS,
    },
}

UI_TEXT = {
    "ko": {
        "language": "언어",
        "data_source": "데이터 소스",
        "source": "소스",
        "range": "조회 범위",
        "x_axis_mode": "시간축 스케일",
        "x_axis_mode_fixed": "고정 스케일",
        "x_axis_mode_auto": "자동 스케일",
        "bucket_minutes": "표시 기간",
        "max_points": "최대 조회 포인트 수",
        "aggregate_caption": (
            "이 값은 차트에 표시할 {bucket} 단위 집계 데이터의 "
            "최대 포인트 수입니다."
        ),
        "auto_refresh": "자동 새로고침",
        "login_title": "대시보드 로그인",
        "login_user": "아이디",
        "login_password": "비밀번호",
        "login_button": "로그인",
        "login_failed": "아이디 또는 비밀번호가 올바르지 않습니다.",
        "login_browser_unsupported": "브라우저 암호화 모듈을 로드하지 못해 로그인할 수 없습니다.",
        "logout": "로그아웃",
        "auth_not_configured": "대시보드 인증이 켜져 있지만 DASHBOARD_AUTH_USERS가 설정되지 않았습니다.",
        "login_success": "로그인되었습니다. 대시보드를 여는 중입니다.",
        "logout_success": "로그아웃되었습니다.",
        "no_rows": "선택한 소스와 조회 범위에 해당하는 데이터가 없습니다.",
        "inverter": "인버터",
        "id": "ID",
        "latest": "최신 시각",
        "ac_output_w": "AC 출력 (W)",
        "status": "상태",
        "fault_normal": "정상",
        "fault_fault": "장애",
        "fault_standby": "대기",
        "utc": "UTC",
        "local": "Local",
        "latest_snapshot": "최신 메트릭",
        "metric_charts": "메트릭 차트",
        "chart_caption": "각 차트는 선택한 조회 범위의 {bucket} 단위 집계값을 표시합니다.",
        "daily_generation_chart": "일일 발전량 (kWh/day)",
        "daily_generation_empty": "선택한 범위에 일일 발전량 데이터가 없습니다.",
        "monthly_generation_chart": "월간 발전량 (kWh/month)",
        "monthly_generation_scope": "월간 차트는 최근 {months}개월 데이터를 별도로 조회합니다.",
        "monthly_generation_empty": "최근 {months}개월에 월간 발전량 데이터가 없습니다.",
        "yearly_generation_chart": "연간 발전량 (kWh/year)",
        "yearly_generation_scope": "연간 차트는 최근 {years}년 데이터를 별도로 조회합니다.",
        "yearly_generation_empty": "최근 {years}년에 연간 발전량 데이터가 없습니다.",
        "fault_events": "장애 이벤트 (최근 200건)",
        "fault_events_caption": "선택한 범위에서 fault_code가 0이 아닌 최신 이벤트입니다.",
        "fault_events_empty": "선택한 범위에서 장애 이벤트가 없습니다.",
        "active_bits": "활성 비트",
        "fault_code_label": "점검 코드 설명",
        "latest_rows": "최신 데이터 (최근 200건)",
    },
    "en": {
        "language": "Language",
        "data_source": "Data Source",
        "source": "Source",
        "range": "Range",
        "x_axis_mode": "Time axis scale",
        "x_axis_mode_fixed": "Fixed scale",
        "x_axis_mode_auto": "Auto scale",
        "bucket_minutes": "Display period",
        "max_points": "Max chart points",
        "aggregate_caption": (
            "This limits the maximum number of {bucket} aggregated chart "
            "points shown."
        ),
        "auto_refresh": "Auto refresh",
        "login_title": "Dashboard Login",
        "login_user": "Username",
        "login_password": "Password",
        "login_button": "Log in",
        "login_failed": "Invalid username or password.",
        "login_browser_unsupported": "Cannot log in because the browser crypto module failed to load.",
        "logout": "Log out",
        "auth_not_configured": "Dashboard authentication is enabled, but DASHBOARD_AUTH_USERS is not set.",
        "login_success": "Login successful. Opening dashboard.",
        "logout_success": "Logged out.",
        "no_rows": "No rows found for the selected source and range.",
        "inverter": "Inverter",
        "id": "ID",
        "latest": "Latest",
        "ac_output_w": "AC Output (W)",
        "status": "Status",
        "fault_normal": "NORMAL",
        "fault_fault": "FAULT",
        "fault_standby": "STANDBY",
        "utc": "UTC",
        "local": "Local",
        "latest_snapshot": "Latest Metrics",
        "metric_charts": "Metric Charts",
        "chart_caption": "Each chart shows {bucket} aggregated values for the selected range.",
        "daily_generation_chart": "Daily Generation (kWh/day)",
        "daily_generation_empty": "No daily generation data in the selected range.",
        "monthly_generation_chart": "Monthly Generation (kWh/month)",
        "monthly_generation_scope": "Monthly chart separately queries the last {months} months.",
        "monthly_generation_empty": "No monthly generation data in the last {months} months.",
        "yearly_generation_chart": "Yearly Generation (kWh/year)",
        "yearly_generation_scope": "Yearly chart separately queries the last {years} years.",
        "yearly_generation_empty": "No yearly generation data in the last {years} years.",
        "fault_events": "Fault Events (Recent 200)",
        "fault_events_caption": "Latest events where fault_code is non-zero within the selected range.",
        "fault_events_empty": "No fault events in the selected range.",
        "active_bits": "Active bits",
        "fault_code_label": "Fault code detail",
        "latest_rows": "Latest Rows (Recent 200)",
    },
}

RANGE_LABELS = {
    "ko": {
        "Last 1 hour": "최근 1시간",
        "Last 6 hours": "최근 6시간",
        "Last 24 hours": "최근 24시간",
        "Today": "오늘",
        "Last 2 days": "최근 2일",
        "Last 3 days": "최근 3일",
        "Last 7 days": "최근 7일",
        "Last 30 days": "최근 30일",
        "Last 90 days": "최근 90일",
        "Last 6 months": "최근 6개월",
    },
    "en": {
        "Last 1 hour": "Last 1 hour",
        "Last 6 hours": "Last 6 hours",
        "Last 24 hours": "Last 24 hours",
        "Today": "Today",
        "Last 2 days": "Last 2 days",
        "Last 3 days": "Last 3 days",
        "Last 7 days": "Last 7 days",
        "Last 30 days": "Last 30 days",
        "Last 90 days": "Last 90 days",
        "Last 6 months": "Last 6 months",
    },
}

BUCKET_SECONDS = [60, 120, 300, 600, 900, 1800, 3600, 10800, 21600, 43200]

BUCKET_LABELS = {
    "ko": {
        60: "1분",
        120: "2분",
        300: "5분",
        600: "10분",
        900: "15분",
        1800: "30분",
        3600: "1시간",
        10800: "3시간",
        21600: "6시간",
        43200: "12시간",
    },
    "en": {
        60: "1 minute",
        120: "2 minutes",
        300: "5 minutes",
        600: "10 minutes",
        900: "15 minutes",
        1800: "30 minutes",
        3600: "1 hour",
        10800: "3 hours",
        21600: "6 hours",
        43200: "12 hours",
    },
}

REFRESH_SECONDS = [0, 60, 120, 300, 600]

REFRESH_LABELS = {
    "ko": {
        0: "끄기",
        60: "1분",
        120: "2분",
        300: "5분",
        600: "10분",
    },
    "en": {
        0: "Off",
        60: "1 minute",
        120: "2 minutes",
        300: "5 minutes",
        600: "10 minutes",
    },
}

TIME_AXIS_FORMAT = "%m-%d %H:%M"
TOOLTIP_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

TABLE_LABELS = {
    "ko": {
        "timestamp": "시각 (Local)",
        "inverter_name": "인버터 이름",
        "inverter_id": "인버터 ID",
        **METRIC_LABELS["ko"],
    },
    "en": {
        "timestamp": "Timestamp (Local)",
        "inverter_name": "Inverter name",
        "inverter_id": "Inverter ID",
        **METRIC_LABELS["en"],
    },
}

DEFAULT_METRICS = [
    *METRICS.keys(),
]

CHART_GROUPS = [
    ["total_generation_kwh"],
    ["input_dc_power_w", "output_ac_power_w"],
    ["input_dc_voltage_v", "output_ac_voltage_v"],
    ["input_dc_current_a", "output_ac_current_a"],
    ["output_ac_power_factor_pct", "output_ac_frequency_hz"],
    ["fault_code"],
]

BAR_CHART_COLORS = {
    "total_generation_kwh": "#16a34a",
    "fault_code": "#be185d",
}

AREA_CHART_COLORS = {
    "input_dc_voltage_v": "#f59e0b",
    "input_dc_current_a": "#f59e0b",
    "input_dc_power_w": "#f59e0b",
    "output_ac_voltage_v": "#3b82f6",
    "output_ac_current_a": "#3b82f6",
    "output_ac_power_w": "#3b82f6",
    "output_ac_power_factor_pct": "#14b8a6",
    "output_ac_frequency_hz": "#6366f1",
}

GENERATION_CHART_COLORS = {
    "daily_generation": "#0891b2",
    "monthly_generation": "#0284c7",
    "yearly_generation": "#0f766e",
}

RANGES = {
    "Last 1 hour": timedelta(hours=1),
    "Last 6 hours": timedelta(hours=6),
    "Last 24 hours": timedelta(hours=24),
    "Today": timedelta(days=1),
    "Last 2 days": timedelta(days=2),
    "Last 3 days": timedelta(days=3),
    "Last 7 days": timedelta(days=7),
    "Last 30 days": timedelta(days=30),
    "Last 90 days": timedelta(days=90),
    "Last 6 months": timedelta(days=183),
}

CALENDAR_DAY_RANGE_NAMES = {
    "Today",
    "Last 2 days",
    "Last 3 days",
    "Last 7 days",
    "Last 30 days",
    "Last 90 days",
    "Last 6 months",
}

MAX_AGGREGATE_METRICS = {
    "total_generation_kwh",
    "fault_code",
}

FAULT_OPERATION_STOP_BIT = 0
FAULT_EVENT_MASK = 0xFFFE

FAULT_BIT_LABELS_KO = {
    0: "인버터 미작동",
    1: "태양전지 과전압",
    2: "태양전지 저전압",
    3: "태양전지 과전류",
    4: "인버터 IGBT 에러",
    5: "인버터 과온",
    6: "계통 과전압",
    7: "계통 저전압",
    8: "계통 과전류",
    9: "계통 과주파수",
    10: "계통 저주파수",
    11: "단독운전(정전)",
    12: "지락(누전)",
}

FAULT_EVENT_BITS = tuple(bit for bit in range(1, 16))
FAULT_ALL_BITS = tuple(bit for bit in range(0, 16))


def get_config_path() -> Path | None:
    system_config = Path("/etc") / CONFIG_FILENAME

    if system_config.is_file():
        return system_config

    current_config = Path.cwd() / CONFIG_FILENAME

    if current_config.is_file():
        return current_config

    return None


def load_config() -> Path | None:
    config_path = get_config_path()

    if config_path is not None:
        load_dotenv(dotenv_path=config_path, override=True)

    return config_path


def get_timezone() -> ZoneInfo:
    timezone_name = os.getenv("TIMEZONE", "Asia/Seoul").strip()

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Seoul")


def get_dashboard_title() -> str:
    return (
        os.getenv("DASHBOARD_TITLE", DEFAULT_DASHBOARD_TITLE).strip()
        or DEFAULT_DASHBOARD_TITLE
    )


def get_dashboard_language() -> str:
    language = os.getenv("DASHBOARD_LANGUAGE", "").strip().lower()

    if language in {"english", "en"}:
        return "en"

    if language in {"korean", "ko"}:
        return "ko"

    return DEFAULT_DASHBOARD_LANGUAGE


def get_dashboard_auto_refresh_seconds() -> int:
    raw = os.getenv(
        "DASHBOARD_AUTO_REFRESH_SECONDS",
        str(DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS),
    ).strip()

    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS

    if value == 0:
        return 0

    if 0 < value < 60:
        return 60

    if value in REFRESH_SECONDS:
        return value

    return DEFAULT_DASHBOARD_AUTO_REFRESH_SECONDS


def get_dashboard_max_points() -> int:
    raw = os.getenv(
        "DASHBOARD_MAX_POINTS",
        str(DEFAULT_DASHBOARD_MAX_POINTS),
    ).strip()

    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DASHBOARD_MAX_POINTS

    return min(300000, max(100, value))


def get_dashboard_time_axis_mode() -> str:
    mode = os.getenv("DASHBOARD_TIME_AXIS_MODE", "").strip().lower()

    if mode in {"fixed", "auto"}:
        return mode

    return DEFAULT_DASHBOARD_TIME_AXIS_MODE


def get_dashboard_default_range() -> str:
    raw = os.getenv("DASHBOARD_DEFAULT_RANGE", "").strip()

    if raw in RANGES:
        return raw

    return DEFAULT_DASHBOARD_RANGE


def get_positive_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()

    try:
        value = int(raw)
    except ValueError:
        return default

    return min(maximum, max(minimum, value))


def get_dashboard_monthly_generation_months() -> int:
    return get_positive_int_env(
        "DASHBOARD_MONTHLY_GENERATION_MONTHS",
        DEFAULT_DASHBOARD_MONTHLY_GENERATION_MONTHS,
        minimum=1,
        maximum=120,
    )


def get_dashboard_yearly_generation_years() -> int:
    return get_positive_int_env(
        "DASHBOARD_YEARLY_GENERATION_YEARS",
        DEFAULT_DASHBOARD_YEARLY_GENERATION_YEARS,
        minimum=1,
        maximum=50,
    )


RGB_COLOR_RE = re.compile(
    r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$",
    re.IGNORECASE,
)


def normalize_chart_color(value: str, fallback: str) -> str:
    color = value.strip()
    if not color:
        return fallback

    if re.fullmatch(r"#[0-9a-fA-F]{6}", color) or re.fullmatch(r"#[0-9a-fA-F]{3}", color):
        return color

    rgb_match = RGB_COLOR_RE.fullmatch(color)
    if rgb_match is None:
        return fallback

    red, green, blue = (int(channel) for channel in rgb_match.groups())
    if any(channel < 0 or channel > 255 for channel in (red, green, blue)):
        return fallback

    return f"rgb({red}, {green}, {blue})"


def get_chart_color(chart_name: str, fallback: str) -> str:
    env_name = f"DASHBOARD_CHART_COLOR_{chart_name.upper()}"
    raw = os.getenv(env_name, "")
    return normalize_chart_color(raw, fallback)


def is_operation_stopped(fault_code: int) -> bool:
    return bool(fault_code & (1 << FAULT_OPERATION_STOP_BIT))


def has_fault_condition(fault_code: int) -> bool:
    return bool(fault_code & FAULT_EVENT_MASK)


def get_fault_code_label(fault_code: int) -> str | None:
    if fault_code <= 0:
        return None

    labels = []

    for bit in range(16):
        if not (fault_code & (1 << bit)):
            continue

        label = FAULT_BIT_LABELS_KO.get(bit)
        if label:
            labels.append(label)

    if not labels:
        return None

    return ", ".join(labels)


def get_fault_labels(fault_code: int, bits: tuple[int, ...]) -> str | None:
    labels = []

    for bit in bits:
        if not (fault_code & (1 << bit)):
            continue

        label = FAULT_BIT_LABELS_KO.get(bit)
        if label:
            labels.append(label)

    if not labels:
        return None

    return ", ".join(labels)


def get_fault_event_rows(fault_code: int, bits: tuple[int, ...]) -> list[str]:
    rows = []

    for bit in bits:
        if not (fault_code & (1 << bit)):
            continue

        label = FAULT_BIT_LABELS_KO.get(bit, f"알 수 없는 비트 {bit}")

        mask_value = 1 << bit
        rows.append(
            f"bit{bit} | 0x{mask_value:04X} | {mask_value} | {label}"
        )

    return rows


def format_active_bits(fault_code: int) -> str:
    if fault_code <= 0:
        return "-"

    bits = [f"Bit {bit}" for bit in range(16) if fault_code & (1 << bit)]
    return ", ".join(bits) if bits else "-"


def is_dashboard_auth_enabled() -> bool:
    value = os.getenv("DASHBOARD_AUTH_ENABLED", "false").strip().lower()
    return value in ("1", "true", "yes", "y", "on")


def hash_dashboard_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        DASHBOARD_AUTH_HASH_ITERATIONS,
    ).hex()
    return (
        f"{DASHBOARD_AUTH_HASH_ALGORITHM}$"
        f"{DASHBOARD_AUTH_HASH_ITERATIONS}$"
        f"{salt}$"
        f"{digest}"
    )


def verify_dashboard_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = encoded_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != DASHBOARD_AUTH_HASH_ALGORITHM:
        return False

    try:
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        ).hex()
    except ValueError:
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def parse_dashboard_password_hash(encoded_hash: str) -> tuple[int, str, str] | None:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = encoded_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return None

    if algorithm != DASHBOARD_AUTH_HASH_ALGORITHM:
        return None

    try:
        bytes.fromhex(salt_hex)
        bytes.fromhex(digest_hex)
    except ValueError:
        return None

    return iterations, salt_hex, digest_hex


def build_dashboard_auth_challenge() -> dict[str, int | str]:
    nonce = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + DASHBOARD_AUTH_CHALLENGE_TTL_SECONDS
    payload = f"{nonce}.{expires_at}"
    signature = sign_dashboard_auth_payload(payload)
    return {
        "nonce": nonce,
        "expires_at": expires_at,
        "signature": signature,
    }


def verify_dashboard_login_proof(
    users: dict[str, str],
    proof_data: dict,
) -> str | None:
    try:
        username = str(proof_data["username"]).strip()
        nonce = str(proof_data["nonce"]).strip()
        expires_at = int(proof_data["expires_at"])
        challenge_signature = str(proof_data["challenge_signature"]).strip().lower()
        proof_hex = str(proof_data["proof"]).strip().lower()
    except (KeyError, TypeError, ValueError):
        return None

    if not username or not nonce or not challenge_signature or not proof_hex:
        return None

    if expires_at <= int(time.time()):
        return None

    expected_challenge_signature = sign_dashboard_auth_payload(f"{nonce}.{expires_at}")
    if not hmac.compare_digest(challenge_signature, expected_challenge_signature):
        return None

    encoded_hash = users.get(username)
    if not encoded_hash:
        return None

    parsed_hash = parse_dashboard_password_hash(encoded_hash)
    if not parsed_hash:
        return None

    _, _, digest_hex = parsed_hash
    try:
        key = bytes.fromhex(digest_hex)
        provided_proof = bytes.fromhex(proof_hex)
    except ValueError:
        return None

    message = f"{username}\n{nonce}\n{expires_at}".encode("utf-8")
    expected_proof = hmac.new(key, message, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_proof, provided_proof):
        return None

    return username


def parse_dashboard_auth_users() -> dict[str, str]:
    raw_users = os.getenv("DASHBOARD_AUTH_USERS", "").strip()
    users = {}

    if not raw_users:
        return users

    for entry in raw_users.split(","):
        entry = entry.strip()
        if not entry:
            continue

        username, separator, encoded_hash = entry.partition(":")
        username = username.strip()
        encoded_hash = encoded_hash.strip()
        if separator and username and encoded_hash:
            users[username] = encoded_hash

    return users


def get_dashboard_auth_cookie_secret() -> str:
    explicit_secret = os.getenv("DASHBOARD_AUTH_COOKIE_SECRET", "").strip()
    if explicit_secret:
        return explicit_secret

    return hashlib.sha256(
        os.getenv("DASHBOARD_AUTH_USERS", "").encode("utf-8")
    ).hexdigest()


def parse_dashboard_auth_cookie_persistent_users() -> set[str]:
    raw_users = os.getenv("DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS", "").strip()

    # Backward compatibility for older configuration key.
    if not raw_users:
        raw_users = os.getenv("DASHBOARD_AUTH_PERSISTENT_USERS", "").strip()

    if not raw_users:
        raw_users = DEFAULT_DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS

    if not raw_users:
        return set()

    return {
        username.strip()
        for username in raw_users.split(",")
        if username.strip()
    }


def get_dashboard_auth_cookie_max_age_seconds(username: str | None = None) -> int:
    if username and username in parse_dashboard_auth_cookie_persistent_users():
        return DASHBOARD_AUTH_PERSISTENT_COOKIE_MAX_AGE_SECONDS

    raw_value = os.getenv(
        "DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS",
        str(DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS),
    ).strip()

    try:
        max_age = int(raw_value)
    except ValueError:
        return DEFAULT_DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS

    return max(1, max_age)


def encode_urlsafe_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_urlsafe_json(value: str) -> dict:
    padded_value = value + ("=" * (-len(value) % 4))
    raw = base64.urlsafe_b64decode(padded_value.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def sign_dashboard_auth_payload(payload: str) -> str:
    secret = get_dashboard_auth_cookie_secret().encode("utf-8")
    return hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()


def get_dashboard_auth_expires_at(username: str) -> int:
    return int(time.time()) + get_dashboard_auth_cookie_max_age_seconds(username)


def build_dashboard_auth_cookie(username: str, expires_at: int) -> str:
    max_age = get_dashboard_auth_cookie_max_age_seconds(username)
    payload = encode_urlsafe_json(
        {
            "username": username,
            "expires_at": expires_at,
        }
    )
    signature = sign_dashboard_auth_payload(payload)
    return f"{payload}.{signature}"


def verify_dashboard_auth_cookie(
    token: str,
    users: dict[str, str],
) -> tuple[str, int] | None:
    try:
        payload, signature = token.split(".", 1)
        expected_signature = sign_dashboard_auth_payload(payload)
        if not hmac.compare_digest(signature, expected_signature):
            return None

        data = decode_urlsafe_json(payload)
        username = str(data["username"])
        expires_at = int(data["expires_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if expires_at < int(time.time()):
        return None

    if username not in users:
        return None

    return username, expires_at


def get_dashboard_auth_cookie(st) -> str:
    try:
        value = st.context.cookies.get(DASHBOARD_AUTH_COOKIE_NAME)
    except Exception:
        return ""

    return value or ""


def get_dashboard_auth_proof(st) -> dict | None:
        try:
                raw = st.context.cookies.get(DASHBOARD_AUTH_PROOF_COOKIE_NAME)
        except Exception:
                return None

        if not raw:
                return None

        try:
                decoded = unquote(raw)
                data = json.loads(decoded)
        except (TypeError, ValueError, json.JSONDecodeError):
                return None

        return data if isinstance(data, dict) else None


def render_dashboard_auth_proof_cookie_script(st, payload: str | None, max_age: int) -> None:
        import streamlit.components.v1 as components

        cookie_name = json.dumps(DASHBOARD_AUTH_PROOF_COOKIE_NAME)
        if payload is None:
                cookie_value = '""'
        else:
                cookie_value = json.dumps(payload)

        components.html(
                f"""
                <script>
                    document.cookie = {cookie_name} + "=" + encodeURIComponent({cookie_value})
                        + "; path=/; max-age=" + {str(max_age)} + "; samesite=lax";
                </script>
                """,
                height=0,
        )


def render_dashboard_login_form(st, text: dict[str, str], users: dict[str, str]) -> None:
    import streamlit.components.v1 as components

    try:
        crypto_js_source = CRYPTO_JS_ASSET_PATH.read_text(encoding="utf-8")
    except OSError:
        st.error(text["login_browser_unsupported"])
        return

    challenge = build_dashboard_auth_challenge()
    user_config = {}
    for username, encoded_hash in users.items():
        parsed = parse_dashboard_password_hash(encoded_hash)
        if not parsed:
            continue

        iterations, salt_hex, _ = parsed
        user_config[username] = {
            "iterations": iterations,
            "salt": salt_hex,
        }

    payload = {
        "labels": {
            "login_failed": text["login_failed"],
            "browser_unsupported": text["login_browser_unsupported"],
        },
        "challenge": {
            "nonce": str(challenge["nonce"]),
            "expires_at": int(challenge["expires_at"]),
            "signature": str(challenge["signature"]),
        },
        "users": user_config,
        "proof_cookie_name": DASHBOARD_AUTH_PROOF_COOKIE_NAME,
    }
    payload_json = json.dumps(payload).replace("</", "<\\/")

    components.html(
        f"""
                <div style="display:flex; flex-direction:column; gap:0.5rem;">
                    <label for="dashboard-login-user" style="font-weight:600;">{html.escape(text["login_user"])} </label>
                    <input id="dashboard-login-user" autocomplete="username"
                                 style="padding:0.5rem; border:1px solid #cbd5e1; border-radius:0.5rem;" />
                    <label for="dashboard-login-password" style="font-weight:600; margin-top:0.25rem;">{html.escape(text["login_password"])} </label>
                    <input id="dashboard-login-password" type="password" autocomplete="current-password"
                                 style="padding:0.5rem; border:1px solid #cbd5e1; border-radius:0.5rem;" />
                    <button id="dashboard-login-submit" type="button"
                                    style="margin-top:0.5rem; padding:0.55rem 0.75rem; border:0; border-radius:0.5rem; background:#2563eb; color:white; font-weight:600; cursor:pointer;">
                        {html.escape(text["login_button"])}
                    </button>
                    <div id="dashboard-login-client-error" style="color:#dc2626; font-size:0.9rem;"></div>
                </div>
                <script>
                    const config = {payload_json};
                    const userInput = document.getElementById("dashboard-login-user");
                    const passInput = document.getElementById("dashboard-login-password");
                    const submitButton = document.getElementById("dashboard-login-submit");
                    const errorBox = document.getElementById("dashboard-login-client-error");

                    function ensureCryptoJsLoaded() {{
                        if (window.CryptoJS) {{
                            return Promise.resolve(window.CryptoJS);
                        }}

                        try {{
                            const script = document.createElement("script");
                            script.type = "text/javascript";
                            script.text = {json.dumps(crypto_js_source)};
                            document.head.appendChild(script);
                        }} catch (error) {{
                            return Promise.reject(new Error(config.labels.browser_unsupported));
                        }}

                        if (!window.CryptoJS) {{
                            return Promise.reject(new Error(config.labels.browser_unsupported));
                        }}

                        return Promise.resolve(window.CryptoJS);
                    }}

                    function setError(message) {{
                        errorBox.textContent = message || "";
                    }}

                    async function buildProof(username, password, selectedUser) {{
                        const CryptoJS = await ensureCryptoJsLoaded();
                        if (!CryptoJS) {{
                            throw new Error(config.labels.browser_unsupported);
                        }}

                        const derivedKey = CryptoJS.PBKDF2(
                            password,
                            CryptoJS.enc.Hex.parse(selectedUser.salt),
                            {{
                                hasher: CryptoJS.algo.SHA256,
                                iterations: Number(selectedUser.iterations),
                                keySize: 256 / 32,
                            }}
                        );

                        const message = `${{username}}\\n${{config.challenge.nonce}}\\n${{config.challenge.expires_at}}`;
                        return CryptoJS.HmacSHA256(
                            message,
                            CryptoJS.enc.Hex.parse(derivedKey.toString(CryptoJS.enc.Hex)),
                        ).toString(CryptoJS.enc.Hex);
                    }}

                    async function submitLogin() {{
                        setError("");
                        const username = userInput.value.trim();
                        const password = passInput.value;
                        if (!username || !password) {{
                            return;
                        }}

                        const selectedUser = config.users[username];
                        if (!selectedUser) {{
                            setError(config.labels.login_failed);
                            passInput.value = "";
                            return;
                        }}

                        try {{
                            submitButton.disabled = true;
                            const proof = await buildProof(username, password, selectedUser);
                            const proofPayload = JSON.stringify({{
                                username,
                                nonce: config.challenge.nonce,
                                expires_at: config.challenge.expires_at,
                                challenge_signature: config.challenge.signature,
                                proof,
                            }});
                            document.cookie = config.proof_cookie_name + "=" + encodeURIComponent(proofPayload)
                                + "; path=/; max-age=120; samesite=lax";
                            passInput.value = "";
                            window.parent.location.reload();
                        }} catch (error) {{
                            setError(error && error.message ? error.message : config.labels.browser_unsupported);
                            submitButton.disabled = false;
                        }}
                    }}

                    submitButton.addEventListener("click", submitLogin);
                    passInput.addEventListener("keydown", (event) => {{
                        if (event.key === "Enter") {{
                            event.preventDefault();
                            submitLogin();
                        }}
                    }});
                </script>
                """,
            height=280,
            )


def clear_dashboard_auth_session(st) -> None:
    st.session_state.pop(DASHBOARD_AUTH_SESSION_KEY, None)
    st.session_state.pop(DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY, None)


def set_dashboard_auth_session(st, username: str, expires_at: int) -> None:
    st.session_state[DASHBOARD_AUTH_SESSION_KEY] = username
    st.session_state[DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY] = expires_at


def get_authenticated_dashboard_user(st, users: dict[str, str]) -> str | None:
    username = st.session_state.get(DASHBOARD_AUTH_SESSION_KEY)
    expires_at = st.session_state.get(DASHBOARD_AUTH_SESSION_EXPIRES_AT_KEY)

    if username not in users:
        clear_dashboard_auth_session(st)
        return None

    try:
        expires_at = int(expires_at)
    except (TypeError, ValueError):
        clear_dashboard_auth_session(st)
        return None

    if expires_at < int(time.time()):
        clear_dashboard_auth_session(st)
        st.session_state[DASHBOARD_AUTH_SESSION_EXPIRED_KEY] = True
        return None

    return username


def render_cookie_script(st, token: str | None, max_age: int) -> None:
    import streamlit.components.v1 as components

    cookie_name = json.dumps(DASHBOARD_AUTH_COOKIE_NAME)
    if token is None:
        cookie_value = '""'
        cookie_max_age = "0"
    else:
        cookie_value = json.dumps(token)
        cookie_max_age = str(max_age)

    components.html(
        f"""
        <script>
          document.cookie = {cookie_name} + "=" + encodeURIComponent({cookie_value})
            + "; path=/; max-age=" + {cookie_max_age} + "; samesite=lax";
          window.parent.location.reload();
        </script>
        """,
        height=0,
    )


def env_bool_text(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()
    return "true" if value in ("1", "true", "yes", "y", "on") else "false"


def has_streamlit_option(args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in args)


def build_streamlit_args(cli_args: list[str]) -> list[str]:
    option_defaults = {
        "--server.address": os.getenv("DASHBOARD_SERVER_ADDRESS", "0.0.0.0"),
        "--server.port": os.getenv("DASHBOARD_SERVER_PORT", "8501"),
        "--server.headless": env_bool_text("DASHBOARD_SERVER_HEADLESS", "true"),
        "--browser.gatherUsageStats": env_bool_text(
            "DASHBOARD_GATHER_USAGE_STATS",
            "false",
        ),
        "--server.runOnSave": env_bool_text("DASHBOARD_RUN_ON_SAVE", "false"),
    }
    streamlit_args = []

    for option, value in option_defaults.items():
        if value and not has_streamlit_option(cli_args, option):
            streamlit_args.extend([option, value])

    return streamlit_args


def get_time_bounds(
    range_name: str,
    display_timezone: ZoneInfo,
) -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(display_timezone)

    if range_name == "Today":
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_local.astimezone(timezone.utc), now_utc

    if range_name in CALENDAR_DAY_RANGE_NAMES:
        range_days = max(1, int(RANGES[range_name].total_seconds() // 86400))
        start_date = now_local.date() - timedelta(days=range_days - 1)
        start_local = datetime.combine(start_date, datetime.min.time(), tzinfo=display_timezone)
        return start_local.astimezone(timezone.utc), now_utc

    return now_utc - RANGES[range_name], now_utc


def shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + offset
    return month_index // 12, month_index % 12 + 1


def get_monthly_generation_time_bounds(
    until: datetime,
    display_timezone: ZoneInfo,
    months: int,
) -> tuple[datetime, datetime]:
    until_local = until.astimezone(display_timezone)
    start_year, start_month = shift_month(
        until_local.year,
        until_local.month,
        -(months - 1),
    )
    start_local = datetime(
        start_year,
        start_month,
        1,
        tzinfo=display_timezone,
    )
    return start_local.astimezone(timezone.utc), until


def get_yearly_generation_time_bounds(
    until: datetime,
    display_timezone: ZoneInfo,
    years: int,
) -> tuple[datetime, datetime]:
    until_local = until.astimezone(display_timezone)
    start_local = datetime(
        until_local.year - years + 1,
        1,
        1,
        tzinfo=display_timezone,
    )
    return start_local.astimezone(timezone.utc), until


def get_recent_month_labels(
    until: datetime,
    display_timezone: ZoneInfo,
    months: int,
) -> list[str]:
    until_local = until.astimezone(display_timezone)
    labels = []

    for offset in range(-(months - 1), 1):
        year, month = shift_month(until_local.year, until_local.month, offset)
        labels.append(f"{year:04d}-{month:02d}")

    return labels


def get_recent_year_labels(
    until: datetime,
    display_timezone: ZoneInfo,
    years: int,
) -> list[str]:
    until_year = until.astimezone(display_timezone).year
    return [str(year) for year in range(until_year - years + 1, until_year + 1)]


def get_min_bucket_seconds_for_range(
    range_name: str,
    display_timezone: ZoneInfo,
    max_points: int,
) -> int:
    since, until = get_time_bounds(range_name, display_timezone)
    duration_seconds = max(
        1.0,
        (until.astimezone(timezone.utc) - since.astimezone(timezone.utc)).total_seconds(),
    )
    required_bucket_seconds = int(math.ceil(duration_seconds / max(1, max_points)))

    for bucket in BUCKET_SECONDS:
        if bucket >= required_bucket_seconds:
            return bucket

    return BUCKET_SECONDS[-1]


def normalize_timestamp_value(value):
    import pandas as pd

    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return pd.NaT

    if pd.isna(timestamp):
        return pd.NaT

    if timestamp.tzinfo is not None:
        return timestamp.tz_convert(timezone.utc)

    return timestamp.tz_localize(timezone.utc)


def normalize_dataframe(df):
    import pandas as pd

    if df.empty:
        return df

    df["timestamp"] = df["timestamp"].map(
        normalize_timestamp_value
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    for column in METRICS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def build_aggregate_selects(quote: str) -> str:
    selects = []

    for column in METRICS:
        function = "MAX" if column in MAX_AGGREGATE_METRICS else "AVG"
        selects.append(f"{function}({quote}{column}{quote}) AS {quote}{column}{quote}")

    return ", ".join(selects)


def merge_mode_fault_code(df, mode_df):
    if df.empty or mode_df.empty:
        return df

    merged = df.merge(
        mode_df,
        on="timestamp",
        how="left",
        suffixes=("", "_mode"),
    )

    if "fault_code_mode" in merged.columns:
        merged["fault_code_mode"] = (
            merged["fault_code_mode"]
            .astype(float)
            .round()
        )
        merged["fault_code"] = merged["fault_code_mode"].combine_first(
            merged.get("fault_code")
        )
        merged = merged.drop(columns=["fault_code_mode"])

    if "fault_code" in merged.columns:
        merged["fault_code"] = merged["fault_code"].fillna(0).round().astype(int)

    return merged


def read_sqlite_fault_code_mode_data(
    database_path: Path,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd

    sql = (
        "SELECT bucket_index, timestamp, fault_code, cnt, last_seen FROM ("
        "  SELECT "
        "    (CAST(strftime('%s', timestamp) AS INTEGER) / ?) AS bucket_index, "
        "    datetime((CAST(strftime('%s', timestamp) AS INTEGER) / ?) * ?, 'unixepoch') AS timestamp, "
        "    CAST(\"fault_code\" AS INTEGER) AS fault_code, "
        "    COUNT(*) AS cnt, "
        "    MAX(timestamp) AS last_seen "
        f"  FROM \"{table}\" "
        "  WHERE timestamp >= ? AND timestamp <= ? "
        "  GROUP BY bucket_index, fault_code"
        ") grouped "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    query_limit = max(1, limit) * 32

    with sqlite3.connect(database_path) as connection:
        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                bucket_seconds,
                since.isoformat(),
                until.isoformat(),
                query_limit,
            ],
        )

    if df.empty:
        return normalize_dataframe(df)

    grouped_df = df.sort_values(
        ["bucket_index", "cnt", "last_seen", "fault_code"],
        ascending=[True, False, False, False],
    )
    mode_df = grouped_df.drop_duplicates(subset=["bucket_index"], keep="first")
    mode_df = mode_df[["timestamp", "fault_code"]].rename(
        columns={"fault_code": "fault_code_mode"}
    )
    mode_df = mode_df.sort_values("timestamp", ascending=False).head(limit)
    return normalize_dataframe(mode_df)


def read_mariadb_fault_code_mode_data(
    config: dict,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd
    import pymysql

    sql = (
        "SELECT bucket_index, `timestamp`, fault_code, cnt, last_seen FROM ("
        "  SELECT "
        "    FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) AS bucket_index, "
        "    FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) * %s) AS `timestamp`, "
        "    CAST(`fault_code` AS SIGNED) AS fault_code, "
        "    COUNT(*) AS cnt, "
        "    MAX(`timestamp`) AS last_seen "
        f"  FROM `{table}` "
        "  WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "  GROUP BY bucket_index, fault_code"
        ") grouped "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

    query_limit = max(1, limit) * 32

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                bucket_seconds,
                since,
                until,
                query_limit,
            ],
        )

    if df.empty:
        return normalize_dataframe(df)

    grouped_df = df.sort_values(
        ["bucket_index", "cnt", "last_seen", "fault_code"],
        ascending=[True, False, False, False],
    )
    mode_df = grouped_df.drop_duplicates(subset=["bucket_index"], keep="first")
    mode_df = mode_df[["timestamp", "fault_code"]].rename(
        columns={"fault_code": "fault_code_mode"}
    )
    mode_df = mode_df.sort_values("timestamp", ascending=False).head(limit)
    return normalize_dataframe(mode_df)


def read_sqlite_fault_events(
    database_path: Path,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
):
    import pandas as pd

    sql = (
        "SELECT timestamp, inverter_name, inverter_id, fault_code "
        f"FROM \"{table}\" "
        "WHERE timestamp >= ? AND timestamp <= ? "
        "AND CAST(\"fault_code\" AS INTEGER) != 0 "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    with sqlite3.connect(database_path) as connection:
        df = pd.read_sql_query(
            sql,
            connection,
            params=[since.isoformat(), until.isoformat(), limit],
        )

    return normalize_dataframe(df)


def read_mariadb_fault_events(
    config: dict,
    table: str,
    since: datetime,
    until: datetime,
    limit: int,
):
    import pandas as pd
    import pymysql

    sql = (
        "SELECT `timestamp`, `inverter_name`, `inverter_id`, `fault_code` "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "AND CAST(`fault_code` AS SIGNED) != 0 "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[since, until, limit],
        )

    return normalize_dataframe(df)


def format_table_header(label: str) -> str:
    return f"<th><strong>{html.escape(label)}</strong></th>"


def format_table_timestamp(value, display_timezone: ZoneInfo) -> str:
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()

        if not isinstance(value, datetime):
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(display_timezone).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def render_data_table(
    df,
    columns: list[str],
    header_labels: dict[str, str],
    display_timezone: ZoneInfo,
) -> str:
    display_df = df[columns].head(200).copy()

    if "timestamp" in display_df.columns:
        display_df["timestamp"] = display_df["timestamp"].map(
            lambda value: format_table_timestamp(value, display_timezone)
        )

    header = "".join(
        format_table_header(header_labels.get(column, column))
        for column in columns
    )
    rows = []

    for _, row in display_df.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            cells.append(f"<td>{html.escape(str(value))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
    <div style="overflow-x: auto; max-height: 520px; border: 1px solid #e5e7eb;">
      <table style="border-collapse: collapse; width: 100%; font-size: 0.875rem;">
        <thead>
          <tr>{header}</tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
    <style>
      table th {{
        position: sticky;
        top: 0;
        background: #f8fafc;
        border-bottom: 1px solid #d1d5db;
        padding: 0.5rem;
        text-align: left;
        white-space: nowrap;
                color: #111827;
                font-weight: 700;
      }}
      table td {{
        border-bottom: 1px solid #e5e7eb;
        padding: 0.45rem 0.5rem;
        white-space: nowrap;
      }}
    </style>
    """


def format_timezone_offset(timestamp) -> str:
    offset = timestamp.utcoffset()
    if offset is None:
        return "+00:00"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def format_timestamp_text(
    timestamp,
    display_timezone: ZoneInfo,
) -> tuple[str, str, str, str]:
    if not hasattr(timestamp, "tz_convert"):
        timestamp = datetime.fromisoformat(str(timestamp))

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    utc_timestamp = timestamp.astimezone(timezone.utc)
    local_timestamp = timestamp.astimezone(display_timezone)

    return (
        utc_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        format_timezone_offset(utc_timestamp),
        format_timezone_offset(local_timestamp),
    )


def render_latest_timestamp(timestamp, text: dict[str, str], display_timezone: ZoneInfo) -> str:
    utc_text, local_text, utc_offset, local_offset = format_timestamp_text(
        timestamp,
        display_timezone,
    )

    return f"""
    <div style="line-height: 1.45;">
      <div style="font-size: 1.05rem; color: #475569; margin-bottom: 0.35rem; font-weight: 600;">
        {html.escape(text["latest"])}
      </div>
      <div style="font-size: 1.2rem; font-weight: 650;">
        {html.escape(local_text)} <span style="color:#64748b;">({html.escape(text["local"])}, {html.escape(local_offset)})</span>
      </div>
      <div style="font-size: 1.2rem; font-weight: 650;">
        {html.escape(utc_text)} <span style="color:#64748b;">({html.escape(text["utc"])}, {html.escape(utc_offset)})</span>
      </div>
    </div>
    """


def require_dashboard_auth(st, text: dict[str, str]) -> bool:
    if not is_dashboard_auth_enabled():
        return True

    users = parse_dashboard_auth_users()
    if not users:
        st.error(text["auth_not_configured"])
        return False

    if get_authenticated_dashboard_user(st, users):
        return True

    if st.session_state.pop(DASHBOARD_AUTH_SESSION_EXPIRED_KEY, False):
        render_cookie_script(st, None, 0)
        return False

    cookie_token = get_dashboard_auth_cookie(st)
    cookie_auth = verify_dashboard_auth_cookie(cookie_token, users)
    if cookie_auth:
        cookie_username, cookie_expires_at = cookie_auth
        set_dashboard_auth_session(st, cookie_username, cookie_expires_at)
        return True

    clear_dashboard_auth_session(st)
    if cookie_token:
        render_cookie_script(st, None, 0)
        return False

    proof_data = get_dashboard_auth_proof(st)
    if proof_data:
        render_dashboard_auth_proof_cookie_script(st, None, 0)
        authenticated_user = verify_dashboard_login_proof(users, proof_data)
        if authenticated_user:
            expires_at = get_dashboard_auth_expires_at(authenticated_user)
            set_dashboard_auth_session(st, authenticated_user, expires_at)
            token = build_dashboard_auth_cookie(authenticated_user, expires_at)
            st.success(text["login_success"])
            render_cookie_script(
                st,
                token,
                get_dashboard_auth_cookie_max_age_seconds(authenticated_user),
            )
            return False

        st.error(text["login_failed"])

    st.subheader(text["login_title"])
    render_dashboard_login_form(st, text, users)

    return False


def render_dashboard_logout(st, text: dict[str, str]) -> None:
    if not is_dashboard_auth_enabled():
        return

    authenticated_user = st.session_state.get(DASHBOARD_AUTH_SESSION_KEY)
    if not authenticated_user:
        return

    st.caption(authenticated_user)
    if st.button(text["logout"], use_container_width=True):
        clear_dashboard_auth_session(st)
        st.success(text["logout_success"])
        render_cookie_script(st, None, 0)


def format_snapshot_value(metric_name: str, value) -> str:
    if value is None:
        return "-"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    if metric_name in {"fault_code", "inverter_id"}:
        return str(int(round(numeric)))

    if metric_name in {
        "total_generation_kwh",
        "daily_generation_kwh",
        "monthly_generation_kwh",
        "yearly_generation_kwh",
    }:
        return f"{numeric:.3f}"

    if metric_name in {
        "input_dc_current_a",
        "output_ac_current_a",
        "output_ac_power_factor_pct",
        "output_ac_frequency_hz",
    }:
        return f"{numeric:.2f}"

    return f"{numeric:.1f}"


def render_latest_metric_board(
    st,
    latest,
    metric_labels: dict[str, str],
    generation_snapshot: dict[str, float] | None = None,
) -> None:
    metric_order = [
        "total_generation_kwh",
        "daily_generation_kwh",
        "monthly_generation_kwh",
        "yearly_generation_kwh",
        "input_dc_power_w",
        "output_ac_power_w",
        "input_dc_voltage_v",
        "output_ac_voltage_v",
        "input_dc_current_a",
        "output_ac_current_a",
        "output_ac_power_factor_pct",
        "output_ac_frequency_hz",
        "fault_code",
    ]
    items = []
    generation_snapshot = generation_snapshot or {}

    for metric_name in metric_order:
        label = metric_labels.get(metric_name, metric_name)
        raw_value = (
            generation_snapshot.get(metric_name)
            if metric_name in generation_snapshot
            else latest.get(metric_name)
        )
        value = format_snapshot_value(metric_name, raw_value)
        items.append(f"""
        <div class="latest-metric">
          <div class="latest-metric-label">{html.escape(label)}</div>
          <div class="latest-metric-value">{html.escape(value)}</div>
        </div>
        """)

    st.markdown(
        f"""
        <div class="latest-metric-grid">
          {''.join(items)}
        </div>
        <style>
          .latest-metric-grid {{
            display: grid;
                        grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1.1rem 2rem;
            margin-top: 0.5rem;
            margin-bottom: 1.5rem;
          }}
          .latest-metric {{
            border-top: 1px solid #e5e7eb;
            padding-top: 0.7rem;
            min-width: 0;
          }}
          .latest-metric-label {{
            color: #475569;
            font-size: 0.86rem;
            line-height: 1.3;
            margin-bottom: 0.25rem;
          }}
          .latest-metric-value {{
            color: #1f2937;
            font-size: 1.85rem;
            line-height: 1.15;
            font-weight: 520;
            word-break: break-word;
          }}
          @media (max-width: 900px) {{
            .latest-metric-grid {{
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
          }}
          @media (max-width: 640px) {{
            .latest-metric-grid {{
                            grid-template-columns: repeat(2, minmax(0, 1fr));
                            gap: 0.9rem 1rem;
                        }}
                        .latest-metric-value {{
                            font-size: 1.55rem;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def chart_title(metric_name: str, metric_labels: dict[str, str]) -> str:
    return metric_labels.get(metric_name, metric_name)


def format_chart_stats(metric_name: str, chart_df, latest: dict) -> str | None:
    if metric_name not in chart_df.columns:
        return None
    values = chart_df[metric_name].dropna()
    if values.empty:
        return None
    latest_val = format_snapshot_value(metric_name, latest.get(metric_name))
    avg = format_snapshot_value(metric_name, values.mean())
    min_ = format_snapshot_value(metric_name, values.min())
    max_ = format_snapshot_value(metric_name, values.max())
    med = format_snapshot_value(metric_name, values.median())
    std = format_snapshot_value(metric_name, values.std()) if len(values) > 1 else "-"
    return f"Latest: {latest_val} / Avg: {avg} / Min: {min_} / Max: {max_} / Med: {med} / Std: {std}"


def format_daily_generation_stats(daily_df) -> str | None:
    if "value" not in daily_df.columns:
        return None
    values = daily_df["value"].dropna()
    if values.empty:
        return None

    latest_val = f"{float(values.iloc[-1]):.3f}"
    avg = f"{float(values.mean()):.3f}"
    min_ = f"{float(values.min()):.3f}"
    max_ = f"{float(values.max()):.3f}"
    med = f"{float(values.median()):.3f}"
    std = f"{float(values.std()):.3f}" if len(values) > 1 else "-"
    return f"Latest: {latest_val} / Avg: {avg} / Min: {min_} / Max: {max_} / Med: {med} / Std: {std}"


def format_period_generation_stats(period_df) -> str | None:
    if "value" not in period_df.columns:
        return None

    values = period_df["value"].dropna()
    if values.empty:
        return None

    latest_val = f"{float(values.iloc[-1]):.3f}"
    avg = f"{float(values.mean()):.3f}"
    min_ = f"{float(values.min()):.3f}"
    max_ = f"{float(values.max()):.3f}"
    med = f"{float(values.median()):.3f}"
    std = f"{float(values.std()):.3f}" if len(values) > 1 else "-"
    return f"Latest: {latest_val} / Avg: {avg} / Min: {min_} / Max: {max_} / Med: {med} / Std: {std}"


def build_nonzero_metric_domain(values) -> list[float] | None:
    numeric_values = []

    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        if math.isnan(numeric) or numeric == 0:
            continue

        numeric_values.append(numeric)

    if not numeric_values:
        return None

    min_value = min(numeric_values)
    max_value = max(numeric_values)

    if min_value == max_value:
        lower = math.floor(min_value) - 1
        upper = math.ceil(max_value) + 1
        return [float(lower), float(upper)]

    padding = (max_value - min_value) * 0.03
    lower = math.floor(min_value - padding)
    upper = math.ceil(max_value + padding)

    if lower == upper:
        upper += 1

    return [float(lower), float(upper)]


def render_area_echart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
        .dropna(subset=["timestamp", "value"])
    )

    if chart_data.empty:
        return

    gap_threshold = timedelta(minutes=30)
    if len(chart_data) >= 2:
        diffs = chart_data["timestamp"].diff().dropna()
        positive_diffs = diffs[diffs > timedelta(0)]
        if not positive_diffs.empty:
            typical_gap_seconds = float(positive_diffs.median().total_seconds())
            gap_threshold = timedelta(
                seconds=max(1800.0, typical_gap_seconds * 1.5)
            )
    points = []
    prev_ts = None
    for _, row in chart_data.iterrows():
        ts = row["timestamp"]
        if prev_ts is not None and (ts - prev_ts) > gap_threshold:
            mid_ts = (prev_ts + (ts - prev_ts) / 2).isoformat()
            points.append([mid_ts, None])
        points.append([ts.isoformat(), round(float(row["value"]), 3)])
        prev_ts = ts

    domain = build_nonzero_metric_domain(chart_data["value"])
    y_min = None
    y_max = None
    if domain is not None:
        y_min, y_max = domain

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    color = get_chart_color(metric_name, AREA_CHART_COLORS.get(metric_name, "#3b82f6"))
    latest_timestamp = chart_data["timestamp"].max().isoformat()
    latest_value = float(chart_data["value"].iloc[-1])
    chart_key = (
        f"echart_area_{metric_name}_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(chart_data)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": {
            "type": "value",
            "scale": True,
            "min": y_min,
            "max": y_max,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "line",
                "showSymbol": False,
                "smooth": True,
                "connectNulls": False,
                "lineStyle": {"width": 2, "color": color},
                "areaStyle": {"opacity": 0.18, "color": color},
                "itemStyle": {"color": color},
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def render_area_chart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    render_area_echart(
        st=st,
        chart_df=chart_df,
        metric_name=metric_name,
        metric_label=metric_label,
        since=since,
        until=until,
        fixed_time_axis=fixed_time_axis,
    )


def render_total_generation_echart(
    st,
    chart_data,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    if chart_data.empty:
        return

    echart_data = chart_data.dropna(subset=["timestamp", "value"]).copy()
    if echart_data.empty:
        return

    points = []
    for _, row in echart_data.iterrows():
        timestamp = row["timestamp"]
        value = row["value"]
        points.append([timestamp.isoformat(), round(float(value), 3)])

    domain = build_nonzero_metric_domain(echart_data["value"])
    y_min = None
    y_max = None
    if domain is not None:
        y_min, y_max = domain

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    latest_timestamp = echart_data["timestamp"].max().isoformat()
    latest_value = float(echart_data["value"].iloc[-1])
    chart_key = (
        "echart_total_generation_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(echart_data)}"
    )

    options = {
        # Auto refresh re-runs the script; disable animation to reduce visual flicker.
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": {
            "type": "value",
            "scale": True,
            "min": y_min,
            "max": y_max,
            "minInterval": 1,
            "axisLabel": {"formatter": "{value}"},
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "line"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "bar",
                "barMaxWidth": 18,
                "itemStyle": {
                    "color": get_chart_color(
                        "total_generation_kwh",
                        BAR_CHART_COLORS["total_generation_kwh"],
                    )
                },
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def render_bar_chart(
    st,
    chart_df,
    metric_name: str,
    metric_label: str,
    since: datetime,
    until: datetime,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    color = get_chart_color(metric_name, BAR_CHART_COLORS.get(metric_name, "#16a34a"))
    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
        .dropna(subset=["timestamp", "value"])
    )

    if chart_data.empty:
        return

    if metric_name == "total_generation_kwh":
        render_total_generation_echart(
            st=st,
            chart_data=chart_data,
            metric_label=metric_label,
            since=since,
            until=until,
            fixed_time_axis=fixed_time_axis,
        )
        return

    points = []
    for _, row in chart_data.iterrows():
        raw_value = float(row["value"])
        if metric_name == "fault_code":
            points.append([row["timestamp"].isoformat(), int(round(raw_value))])
        else:
            points.append([row["timestamp"].isoformat(), round(raw_value, 3)])

    x_axis = {
        "type": "time",
        "axisLabel": {
            "formatter": "{MM}-{dd} {HH}:{mm}",
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    if fixed_time_axis:
        x_axis["min"] = since.isoformat()
        x_axis["max"] = until.isoformat()

    y_axis = {
        "type": "value",
        "scale": True,
    }

    if metric_name == "fault_code":
        y_axis["min"] = 0
        y_axis["minInterval"] = 1
        y_axis["axisLabel"] = {"formatter": "{value}"}

    latest_timestamp = chart_data["timestamp"].max().isoformat()
    latest_value = float(chart_data["value"].iloc[-1])
    chart_key = (
        f"echart_bar_{metric_name}_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(chart_data)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": y_axis,
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "bar",
                "barMaxWidth": 18,
                "itemStyle": {"color": color},
                "data": points,
            }
        ],
    }

    st_echarts(
        options=options,
        height="320px",
        renderer="svg",
        key=chart_key,
    )


def validate_bucket_seconds(bucket_seconds: int) -> int:
    if bucket_seconds not in BUCKET_SECONDS:
        raise RuntimeError(f"Invalid aggregation interval: {bucket_seconds}")

    return bucket_seconds


def read_sqlite_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd

    bucket_seconds = validate_bucket_seconds(bucket_seconds)
    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")

    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    metric_selects = build_aggregate_selects('"')
    sql = (
        "SELECT "
        "datetime((CAST(strftime('%s', timestamp) AS INTEGER) / ?) * ?, 'unixepoch') "
        "AS timestamp, "
        'MIN("inverter_name") AS "inverter_name", '
        'MIN("inverter_id") AS "inverter_id", '
        f"{metric_selects} "
        f'FROM "{table}" '
        "WHERE timestamp >= ? AND timestamp <= ? "
        "GROUP BY (CAST(strftime('%s', timestamp) AS INTEGER) / ?) "
        "ORDER BY timestamp DESC LIMIT ?"
    )

    with sqlite3.connect(database_path) as connection:
        ensure_sqlite_table(connection, table)
        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                since.isoformat(),
                until.isoformat(),
                bucket_seconds,
                limit,
            ],
        )

    # Keep fault_code as bucket MAX so brief non-zero events are not diluted.
    return normalize_dataframe(df)


def read_mariadb_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_seconds: int,
):
    import pandas as pd
    import pymysql

    bucket_seconds = validate_bucket_seconds(bucket_seconds)
    config = get_mariadb_config()
    validate_mariadb_config(config)
    table = require_mariadb_identifier(config["table"], "table")
    metric_selects = build_aggregate_selects("`")
    sql = (
        "SELECT "
        "FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) * %s) AS `timestamp`, "
        "MIN(`inverter_name`) AS `inverter_name`, "
        "MIN(`inverter_id`) AS `inverter_id`, "
        f"{metric_selects} "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "GROUP BY FLOOR(UNIX_TIMESTAMP(`timestamp`) / %s) "
        "ORDER BY `timestamp` DESC LIMIT %s"
    )

    since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
    until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[
                bucket_seconds,
                bucket_seconds,
                since_naive,
                until_naive,
                bucket_seconds,
                limit,
            ],
        )

    # Keep fault_code as bucket MAX so brief non-zero events are not diluted.
    return normalize_dataframe(df)


def read_fault_events(
    source: str,
    since: datetime,
    until: datetime,
    limit: int = 200,
):
    if source == "MariaDB":
        config = get_mariadb_config()
        validate_mariadb_config(config)
        table = require_mariadb_identifier(config["table"], "table")
        since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
        until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)
        return read_mariadb_fault_events(
            config=config,
            table=table,
            since=since_naive,
            until=until_naive,
            limit=limit,
        )

    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")
    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    return read_sqlite_fault_events(
        database_path=database_path,
        table=table,
        since=since,
        until=until,
        limit=limit,
    )


def read_mariadb_latest_status_sample(
    config: dict,
    table: str,
    since: datetime,
    until: datetime,
):
    import pandas as pd
    import pymysql

    sql = (
        "SELECT `timestamp`, `inverter_name`, `inverter_id`, "
        "CAST(`fault_code` AS SIGNED) AS `fault_code` "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "ORDER BY `timestamp` DESC LIMIT 1"
    )

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[since, until],
        )

    return normalize_dataframe(df)


def read_sqlite_latest_status_sample(
    database_path: Path,
    table: str,
    since: datetime,
    until: datetime,
):
    import pandas as pd

    sql = (
        "SELECT timestamp, inverter_name, inverter_id, "
        "CAST(\"fault_code\" AS INTEGER) AS fault_code "
        f"FROM \"{table}\" "
        "WHERE timestamp >= ? AND timestamp <= ? "
        "ORDER BY timestamp DESC LIMIT 1"
    )

    with sqlite3.connect(database_path) as connection:
        df = pd.read_sql_query(
            sql,
            connection,
            params=[since.isoformat(), until.isoformat()],
        )

    return normalize_dataframe(df)


def read_latest_status_sample(
    source: str,
    since: datetime,
    until: datetime,
):
    if source == "MariaDB":
        config = get_mariadb_config()
        validate_mariadb_config(config)
        table = require_mariadb_identifier(config["table"], "table")
        since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
        until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)
        return read_mariadb_latest_status_sample(
            config=config,
            table=table,
            since=since_naive,
            until=until_naive,
        )

    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")
    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    return read_sqlite_latest_status_sample(
        database_path=database_path,
        table=table,
        since=since,
        until=until,
    )


def read_mariadb_daily_generation(
    since: datetime,
    until: datetime,
    display_timezone: ZoneInfo,
):
    import pandas as pd
    import pymysql

    config = get_mariadb_config()
    validate_mariadb_config(config)
    table = require_mariadb_identifier(config["table"], "table")

    since_naive = since.astimezone(timezone.utc).replace(tzinfo=None)
    until_naive = until.astimezone(timezone.utc).replace(tzinfo=None)

    offset_text = format_timezone_offset(datetime.now(timezone.utc).astimezone(display_timezone))
    sql = (
        "SELECT "
        "DATE(CONVERT_TZ(`timestamp`, '+00:00', %s)) AS day_local, "
        "GREATEST("
        "MAX(`total_generation_kwh`) - "
        "COALESCE(MIN(NULLIF(`total_generation_kwh`, 0)), MAX(`total_generation_kwh`)), "
        "0"
        ") AS daily_generation_kwh "
        f"FROM `{table}` "
        "WHERE `timestamp` >= %s AND `timestamp` <= %s "
        "GROUP BY day_local "
        "ORDER BY day_local ASC"
    )

    with pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=config["connect_timeout"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

        df = pd.read_sql_query(
            sql,
            connection,
            params=[offset_text, since_naive, until_naive],
        )

    if df.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    def to_utc_timestamp(day_text: str):
        local_dt = datetime.fromisoformat(str(day_text)).replace(tzinfo=display_timezone)
        return local_dt.astimezone(timezone.utc)

    result = pd.DataFrame(
        {
            "timestamp": [to_utc_timestamp(day) for day in df["day_local"]],
            "value": pd.to_numeric(df["daily_generation_kwh"], errors="coerce").fillna(0.0),
        }
    )
    return result


def read_sqlite_daily_generation(
    since: datetime,
    until: datetime,
    display_timezone: ZoneInfo,
):
    import pandas as pd

    config = get_sqlite_config()
    database_path = Path(config["path"]).expanduser()
    table = require_sqlite_identifier(config["table"], "table")

    if not database_path.is_file():
        raise RuntimeError(f"SQLite database not found: {database_path}")

    offset_text = format_timezone_offset(datetime.now(timezone.utc).astimezone(display_timezone))
    sql = (
        "SELECT "
        "date(datetime(CAST(strftime('%s', timestamp) AS INTEGER), 'unixepoch', ?)) AS day_local, "
        "MAX(CAST(\"total_generation_kwh\" AS REAL)) - "
        "COALESCE(MIN(NULLIF(CAST(\"total_generation_kwh\" AS REAL), 0)), "
        "MAX(CAST(\"total_generation_kwh\" AS REAL))) AS daily_generation_kwh "
        f"FROM \"{table}\" "
        "WHERE timestamp >= ? AND timestamp <= ? "
        "GROUP BY day_local "
        "ORDER BY day_local ASC"
    )

    with sqlite3.connect(database_path) as connection:
        ensure_sqlite_table(connection, table)
        df = pd.read_sql_query(
            sql,
            connection,
            params=[offset_text, since.isoformat(), until.isoformat()],
        )

    if df.empty:
        return pd.DataFrame(columns=["timestamp", "value"])

    def to_utc_timestamp(day_text: str):
        local_dt = datetime.fromisoformat(str(day_text)).replace(tzinfo=display_timezone)
        return local_dt.astimezone(timezone.utc)

    values = pd.to_numeric(df["daily_generation_kwh"], errors="coerce").fillna(0.0)
    values = values.clip(lower=0.0)
    result = pd.DataFrame(
        {
            "timestamp": [to_utc_timestamp(day) for day in df["day_local"]],
            "value": values,
        }
    )
    return result


def read_daily_generation(
    source: str,
    since: datetime,
    until: datetime,
    display_timezone: ZoneInfo,
):
    if source == "MariaDB":
        return read_mariadb_daily_generation(
            since=since,
            until=until,
            display_timezone=display_timezone,
        )

    return read_sqlite_daily_generation(
        since=since,
        until=until,
        display_timezone=display_timezone,
    )


def coerce_utc_datetime(value) -> datetime:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    elif not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def build_generation_snapshot(
    daily_df,
    latest_timestamp,
    display_timezone: ZoneInfo,
) -> dict[str, float]:
    latest_utc = coerce_utc_datetime(latest_timestamp)
    latest_local = latest_utc.astimezone(display_timezone)

    if daily_df.empty:
        return {}

    monthly_df = aggregate_generation_by_period(
        daily_df=daily_df,
        display_timezone=display_timezone,
        period="month",
    )
    yearly_df = aggregate_generation_by_period(
        daily_df=daily_df,
        display_timezone=display_timezone,
        period="year",
    )

    current_day = latest_local.strftime("%Y-%m-%d")
    current_month = latest_local.strftime("%Y-%m")
    current_year = latest_local.strftime("%Y")

    daily_values: dict[str, float] = {}
    for _, row in daily_df.iterrows():
        timestamp = row["timestamp"]
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        if not isinstance(timestamp, datetime):
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        label = timestamp.astimezone(display_timezone).strftime("%Y-%m-%d")
        daily_values[label] = daily_values.get(label, 0.0) + float(row["value"])

    monthly_values = {
        str(row["label"]): float(row["value"])
        for _, row in monthly_df.iterrows()
    }
    yearly_values = {
        str(row["label"]): float(row["value"])
        for _, row in yearly_df.iterrows()
    }

    return {
        "daily_generation_kwh": daily_values.get(current_day, 0.0),
        "monthly_generation_kwh": monthly_values.get(current_month, 0.0),
        "yearly_generation_kwh": yearly_values.get(current_year, 0.0),
    }


def filter_daily_generation_by_range(
    daily_df,
    since: datetime,
    until: datetime,
    display_timezone: ZoneInfo,
):
    if daily_df.empty:
        return daily_df

    filtered_df = daily_df.copy()
    filtered_df["timestamp"] = filtered_df["timestamp"].map(coerce_utc_datetime)
    since_date = since.astimezone(display_timezone).date()
    until_date = until.astimezone(display_timezone).date()
    local_dates = filtered_df["timestamp"].map(
        lambda value: value.astimezone(display_timezone).date()
    )
    return filtered_df[
        (local_dates >= since_date)
        & (local_dates <= until_date)
    ]


def render_fault_events_table(
    st,
    fault_events_df,
    text: dict[str, str],
    lang: str,
    display_timezone: ZoneInfo,
) -> None:
    import pandas as pd

    if fault_events_df.empty:
        st.caption(text["fault_events_empty"])
        return

    display_df = fault_events_df.copy()
    display_df = display_df.sort_values("timestamp", ascending=False).head(200)
    display_df["fault_code"] = pd.to_numeric(
        display_df["fault_code"],
        errors="coerce",
    ).fillna(0).astype(int)
    display_df[text["active_bits"]] = display_df["fault_code"].map(
        lambda code: format_active_bits(int(code))
    )
    display_df[text["fault_code_label"]] = display_df["fault_code"].map(
        lambda code: get_fault_code_label(int(code)) or f"FAULT CODE {int(code)}"
    )

    columns = [
        "timestamp",
        "inverter_name",
        "inverter_id",
        "fault_code",
        text["active_bits"],
        text["fault_code_label"],
    ]
    header_labels = {
        "timestamp": TABLE_LABELS[lang]["timestamp"],
        "inverter_name": TABLE_LABELS[lang]["inverter_name"],
        "inverter_id": TABLE_LABELS[lang]["inverter_id"],
        "fault_code": TABLE_LABELS[lang]["fault_code"],
        text["active_bits"]: text["active_bits"],
        text["fault_code_label"]: text["fault_code_label"],
    }

    st.markdown(
        render_data_table(
            display_df.sort_values("timestamp", ascending=False),
            columns,
            header_labels,
            display_timezone,
        ),
        unsafe_allow_html=True,
    )


def render_daily_generation_chart(
    st,
    daily_df,
    title: str,
    since: datetime,
    until: datetime,
    display_timezone: ZoneInfo,
    fixed_time_axis: bool,
) -> None:
    from streamlit_echarts import st_echarts

    chart_data = daily_df.dropna(subset=["timestamp", "value"]).copy()

    value_by_day: dict[str, float] = {}
    if not chart_data.empty:
        chart_data = chart_data.sort_values("timestamp")
        for _, row in chart_data.iterrows():
            timestamp = row["timestamp"]
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if not isinstance(timestamp, datetime):
                continue

            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            day_label = timestamp.astimezone(display_timezone).strftime("%Y-%m-%d")
            value_by_day[day_label] = value_by_day.get(day_label, 0.0) + float(row["value"])

    if fixed_time_axis:
        end_day = until.astimezone(display_timezone).date()
        duration_seconds = max(
            0.0,
            (until.astimezone(timezone.utc) - since.astimezone(timezone.utc)).total_seconds(),
        )
        day_count = max(1, math.ceil(duration_seconds / 86400.0))
        start_day = end_day - timedelta(days=day_count - 1)
        categories = [
            (start_day + timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(day_count)
        ]
    else:
        categories = sorted(value_by_day.keys())

    if not categories:
        return

    values = [round(float(value_by_day.get(day, 0.0)), 3) for day in categories]

    x_axis = {
        "type": "category",
        "data": categories,
        "axisTick": {
            "show": True,
            "alignWithLabel": True,
            "interval": 0,
        },
        "axisLabel": {
            "hideOverlap": True,
            "interval": "auto",
        },
    }

    latest_timestamp = categories[-1]
    latest_value = float(values[-1])
    chart_key = (
        "echart_daily_generation_"
        f"{latest_timestamp}_"
        f"{latest_value:.6f}_"
        f"{len(categories)}_"
        f"{int(fixed_time_axis)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": x_axis,
        "yAxis": {
            "type": "value",
            "scale": True,
            "min": 0,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "series": [
            {
                "name": title,
                "type": "bar",
                "barMaxWidth": 42,
                "barMinWidth": 16,
                "itemStyle": {
                    "color": get_chart_color(
                        "daily_generation",
                        GENERATION_CHART_COLORS["daily_generation"],
                    )
                },
                "data": values,
            }
        ],
    }

    st_echarts(
        options=options,
        height="300px",
        renderer="svg",
        key=chart_key,
    )


def aggregate_generation_by_period(
    daily_df,
    display_timezone: ZoneInfo,
    period: str,
):
    import pandas as pd

    chart_data = daily_df.dropna(subset=["timestamp", "value"]).copy()
    if chart_data.empty:
        return pd.DataFrame(columns=["label", "value"])

    chart_data = chart_data.sort_values("timestamp")
    labels: list[str] = []
    for timestamp in chart_data["timestamp"]:
        value = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        if not isinstance(value, datetime):
            labels.append("")
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local_dt = value.astimezone(display_timezone)
        if period == "month":
            labels.append(local_dt.strftime("%Y-%m"))
        else:
            labels.append(local_dt.strftime("%Y"))

    chart_data["period_label"] = labels
    chart_data = chart_data[chart_data["period_label"] != ""]
    if chart_data.empty:
        return pd.DataFrame(columns=["label", "value"])

    grouped = (
        chart_data.groupby("period_label", as_index=False)["value"]
        .sum()
        .sort_values("period_label")
        .rename(columns={"period_label": "label"})
    )
    grouped["value"] = pd.to_numeric(grouped["value"], errors="coerce").fillna(0.0)
    return grouped


def fill_period_generation_labels(period_df, labels: list[str]):
    import pandas as pd

    if not labels:
        return pd.DataFrame(columns=["label", "value"])

    values_by_label = {}
    if not period_df.empty:
        for _, row in period_df.iterrows():
            values_by_label[str(row["label"])] = float(row["value"])

    return pd.DataFrame(
        {
            "label": labels,
            "value": [values_by_label.get(label, 0.0) for label in labels],
        }
    )


def render_period_generation_chart(
    st,
    period_df,
    title: str,
    chart_key_prefix: str,
    color: str,
) -> None:
    from streamlit_echarts import st_echarts

    if period_df.empty:
        return

    categories = period_df["label"].astype(str).tolist()
    values = [round(float(value), 3) for value in period_df["value"].tolist()]
    if not categories:
        return

    chart_key = (
        f"{chart_key_prefix}_"
        f"{categories[-1]}_"
        f"{values[-1]:.6f}_"
        f"{len(categories)}"
    )

    options = {
        "animation": False,
        "grid": {"left": 70, "right": 24, "top": 24, "bottom": 56},
        "xAxis": {
            "type": "category",
            "data": categories,
            "axisTick": {
                "show": True,
                "alignWithLabel": True,
                "interval": 0,
            },
            "axisLabel": {
                "hideOverlap": True,
                "interval": "auto",
            },
        },
        "yAxis": {
            "type": "value",
            "scale": True,
            "min": 0,
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
        },
        "series": [
            {
                "name": title,
                "type": "bar",
                "barMaxWidth": 42,
                "barMinWidth": 16,
                "itemStyle": {"color": color},
                "data": values,
            }
        ],
    }

    st_echarts(
        options=options,
        height="300px",
        renderer="svg",
        key=chart_key,
    )


def render_dashboard_body(
    st,
    source: str,
    range_name: str,
    bucket_seconds: int,
    limit: int,
    text: dict[str, str],
    metric_labels: dict[str, str],
    lang: str,
    dashboard_title: str,
    display_timezone: ZoneInfo,
    fixed_time_axis: bool,
) -> None:
    since, until = get_time_bounds(range_name, display_timezone)

    try:
        if source == "MariaDB":
            df = read_mariadb_data(
                since,
                until,
                int(limit),
                bucket_seconds,
            )
        else:
            df = read_sqlite_data(
                since,
                until,
                int(limit),
                bucket_seconds,
            )
    except Exception as e:
        st.error(str(e))
        return

    if df.empty:
        st.warning(text["no_rows"])
        return

    latest = df.sort_values("timestamp").iloc[-1]
    latest_utc = coerce_utc_datetime(latest["timestamp"])
    latest_local = latest_utc.astimezone(display_timezone)
    latest_year_start = datetime(
        latest_local.year,
        1,
        1,
        tzinfo=display_timezone,
    ).astimezone(timezone.utc)
    monthly_generation_months = get_dashboard_monthly_generation_months()
    yearly_generation_years = get_dashboard_yearly_generation_years()
    monthly_generation_since, _ = get_monthly_generation_time_bounds(
        until=until,
        display_timezone=display_timezone,
        months=monthly_generation_months,
    )
    yearly_generation_since, _ = get_yearly_generation_time_bounds(
        until=until,
        display_timezone=display_timezone,
        years=yearly_generation_years,
    )
    monthly_generation_labels = get_recent_month_labels(
        until=until,
        display_timezone=display_timezone,
        months=monthly_generation_months,
    )
    yearly_generation_labels = get_recent_year_labels(
        until=until,
        display_timezone=display_timezone,
        years=yearly_generation_years,
    )
    generation_since = min(
        since.astimezone(timezone.utc),
        latest_year_start,
        monthly_generation_since,
        yearly_generation_since,
    )
    daily_generation_df = None
    daily_generation_error = None

    try:
        daily_generation_df = read_daily_generation(
            source=source,
            since=generation_since,
            until=until,
            display_timezone=display_timezone,
        )
    except Exception as e:
        daily_generation_error = e

    status_sample = latest
    try:
        status_df = read_latest_status_sample(source, since, until)
    except Exception:
        status_df = None

    if status_df is not None and not status_df.empty:
        status_sample = status_df.sort_values("timestamp").iloc[-1]

    inverter_name = status_sample.get("inverter_name", latest.get("inverter_name", ""))
    inverter_id = int(status_sample.get("inverter_id", latest.get("inverter_id", 0)))
    try:
        fault_code = int(status_sample.get("fault_code", 0))
    except (TypeError, ValueError):
        fault_code = 0

    operation_stopped = is_operation_stopped(fault_code)
    has_fault = has_fault_condition(fault_code)

    if has_fault:
        fault_label = text["fault_fault"]
        fault_color = "#dc2626"
        fault_bg = "#fee2e2"
    elif operation_stopped:
        fault_label = text["fault_standby"]
        fault_color = "#475569"
        fault_bg = "#e2e8f0"
    else:
        fault_label = text["fault_normal"]
        fault_color = "#16a34a"
        fault_bg = "#dcfce7"

    fault_badge_text = fault_label

    operation_label = FAULT_BIT_LABELS_KO.get(FAULT_OPERATION_STOP_BIT)
    fault_event_labels = get_fault_labels(fault_code, FAULT_EVENT_BITS)

    if fault_code != 0:
        detail_rows = get_fault_event_rows(fault_code, FAULT_ALL_BITS)
        if detail_rows:
            detail_text = "\n".join(detail_rows)
        else:
            detail_text = fault_event_labels or f"FAULT CODE {fault_code}"
        fault_code_detail = detail_text
    else:
        detail_text = text["fault_normal"]
        fault_code_detail = detail_text

    st.markdown(
        f"""
        <div style="
            font-size: 1.75rem;
            line-height: 1.35;
            margin-bottom: 1rem;
            font-weight: 650;
            color: #1f2937;
        ">
          <strong>{text["inverter"]}:</strong> {html.escape(str(inverter_name))}
          <span style="margin-left: 1.5rem;"><strong>{text["id"]}:</strong> {inverter_id}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_columns = st.columns([2, 1])
    with summary_columns[0]:
        st.markdown(
            render_latest_timestamp(latest["timestamp"], text, display_timezone),
            unsafe_allow_html=True,
        )
    summary_columns[1].markdown(
        f"""
        <div style="font-size: 0.875rem; margin-bottom: 0.25rem;">{text["status"]}</div>
        <div style="
            display: inline-flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 0.2rem;
            padding: 0.45rem 0.7rem;
            border-radius: 0.4rem;
            color: {fault_color};
            background: {fault_bg};
            border: 1px solid {fault_color};
            font-weight: 700;
            letter-spacing: 0.02em;
            min-width: 22rem;
            max-width: 100%;
        ">
            <div>{fault_badge_text}</div>
            <div style="font-size:0.74rem; font-weight:600; white-space:pre-line; overflow-wrap:anywhere; max-width:40rem; opacity:0.95;">{html.escape(fault_code_detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height: 1.25rem;"></div>', unsafe_allow_html=True)
    st.subheader(text["latest_snapshot"])
    if daily_generation_df is not None:
        generation_snapshot = build_generation_snapshot(
            daily_df=daily_generation_df,
            latest_timestamp=latest["timestamp"],
            display_timezone=display_timezone,
        )
    else:
        generation_snapshot = {}
    render_latest_metric_board(
        st,
        latest,
        metric_labels,
        generation_snapshot=generation_snapshot,
    )

    chart_df = df.sort_values("timestamp").set_index("timestamp")

    for group in CHART_GROUPS:
        if len(group) == 1:
            metric_name = group[0]
            st.markdown(f"#### {chart_title(metric_name, metric_labels)}")
            stats = format_chart_stats(metric_name, chart_df, latest)
            if stats:
                st.caption(stats)
            if metric_name in BAR_CHART_COLORS:
                render_bar_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                    since,
                    until,
                    fixed_time_axis,
                )
            else:
                render_area_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                    since,
                    until,
                    fixed_time_axis,
                )

            if metric_name == "total_generation_kwh":
                if daily_generation_error is not None:
                    st.warning(str(daily_generation_error))
                else:
                    daily_df = filter_daily_generation_by_range(
                        daily_generation_df,
                        since=since,
                        until=until,
                        display_timezone=display_timezone,
                    )
                    if daily_df.empty and not fixed_time_axis:
                        st.caption(text["daily_generation_empty"])
                    else:
                        st.markdown(f"#### {text['daily_generation_chart']}")
                        daily_stats = format_daily_generation_stats(daily_df)
                        if daily_stats:
                            st.caption(daily_stats)
                        render_daily_generation_chart(
                            st=st,
                            daily_df=daily_df,
                            title=text["daily_generation_chart"],
                            since=since,
                            until=until,
                            display_timezone=display_timezone,
                            fixed_time_axis=fixed_time_axis,
                        )

                    monthly_daily_df = filter_daily_generation_by_range(
                        daily_generation_df,
                        since=monthly_generation_since,
                        until=until,
                        display_timezone=display_timezone,
                    )
                    yearly_daily_df = filter_daily_generation_by_range(
                        daily_generation_df,
                        since=yearly_generation_since,
                        until=until,
                        display_timezone=display_timezone,
                    )
                    monthly_raw_df = aggregate_generation_by_period(
                        daily_df=monthly_daily_df,
                        display_timezone=display_timezone,
                        period="month",
                    )
                    yearly_raw_df = aggregate_generation_by_period(
                        daily_df=yearly_daily_df,
                        display_timezone=display_timezone,
                        period="year",
                    )
                    if fixed_time_axis:
                        monthly_df = fill_period_generation_labels(
                            monthly_raw_df,
                            monthly_generation_labels,
                        )
                        yearly_df = fill_period_generation_labels(
                            yearly_raw_df,
                            yearly_generation_labels,
                        )
                    else:
                        monthly_df = monthly_raw_df
                        yearly_df = yearly_raw_df

                    monthly_col, yearly_col = st.columns(2)
                    with monthly_col:
                        st.markdown(f"#### {text['monthly_generation_chart']}")
                        st.caption(
                            text["monthly_generation_scope"].format(
                                months=monthly_generation_months,
                            )
                        )
                        if monthly_raw_df.empty:
                            st.caption(
                                text["monthly_generation_empty"].format(
                                    months=monthly_generation_months,
                                )
                            )
                        else:
                            monthly_stats = format_period_generation_stats(monthly_df)
                            if monthly_stats:
                                st.caption(monthly_stats)
                        render_period_generation_chart(
                            st=st,
                            period_df=monthly_df,
                            title=text["monthly_generation_chart"],
                            chart_key_prefix="echart_monthly_generation",
                            color=get_chart_color(
                                "monthly_generation",
                                GENERATION_CHART_COLORS["monthly_generation"],
                            ),
                        )

                    with yearly_col:
                        st.markdown(f"#### {text['yearly_generation_chart']}")
                        st.caption(
                            text["yearly_generation_scope"].format(
                                years=yearly_generation_years,
                            )
                        )
                        if yearly_raw_df.empty:
                            st.caption(
                                text["yearly_generation_empty"].format(
                                    years=yearly_generation_years,
                                )
                            )
                        else:
                            yearly_stats = format_period_generation_stats(yearly_df)
                            if yearly_stats:
                                st.caption(yearly_stats)
                        render_period_generation_chart(
                            st=st,
                            period_df=yearly_df,
                            title=text["yearly_generation_chart"],
                            chart_key_prefix="echart_yearly_generation",
                            color=get_chart_color(
                                "yearly_generation",
                                GENERATION_CHART_COLORS["yearly_generation"],
                            ),
                        )
            continue

        chart_columns = st.columns(2)

        for column, metric_name in zip(chart_columns, group):
            with column:
                st.markdown(f"#### {chart_title(metric_name, metric_labels)}")
                stats = format_chart_stats(metric_name, chart_df, latest)
                if stats:
                    st.caption(stats)
                if metric_name in BAR_CHART_COLORS:
                    render_bar_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                        since,
                        until,
                        fixed_time_axis,
                    )
                else:
                    render_area_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                        since,
                        until,
                        fixed_time_axis,
                    )

    st.subheader(text["fault_events"])
    st.caption(text["fault_events_caption"])
    try:
        fault_events_df = read_fault_events(source, since, until, limit=200)
    except Exception as e:
        st.warning(str(e))
    else:
        render_fault_events_table(st, fault_events_df, text, lang, display_timezone)

    st.subheader(text["latest_rows"])
    display_columns = [
        "timestamp",
        "inverter_name",
        "inverter_id",
        "total_generation_kwh",
        *[
            metric_name
            for metric_name in DEFAULT_METRICS
            if metric_name != "total_generation_kwh"
        ],
    ]
    st.markdown(
        render_data_table(
            df.sort_values("timestamp", ascending=False),
            display_columns,
            {column: TABLE_LABELS[lang].get(column, column) for column in display_columns},
            display_timezone,
        ),
        unsafe_allow_html=True,
    )


def run_app() -> None:
    import streamlit as st

    load_config()
    dashboard_title = get_dashboard_title()
    display_timezone = get_timezone()

    st.set_page_config(
        page_title=dashboard_title,
        layout="wide",
    )

    auth_text = UI_TEXT["en"]
    st.title(dashboard_title)
    if not require_dashboard_auth(st, auth_text):
        return

    def get_query_param(name: str) -> str | None:
        if not hasattr(st, "query_params"):
            return None

        raw = st.query_params.get(name)
        if isinstance(raw, list):
            raw = raw[0] if raw else None

        if raw is None:
            return None

        value = str(raw).strip()
        return value or None

    with st.sidebar:
        if "dashboard_lang" not in st.session_state:
            st.session_state["dashboard_lang"] = get_dashboard_language()

        query_lang = get_query_param("lang")
        if query_lang in {"ko", "en"}:
            st.session_state["dashboard_lang"] = query_lang

        current_lang = st.session_state["dashboard_lang"]
        if current_lang not in {"ko", "en"}:
            current_lang = get_dashboard_language()
            st.session_state["dashboard_lang"] = current_lang

        language_choice = st.selectbox(
            UI_TEXT[current_lang]["language"],
            ["ko", "en"],
            index=0 if current_lang == "ko" else 1,
            format_func=lambda value: "한국어" if value == "ko" else "English",
            key="dashboard_lang_selector",
        )

        if language_choice != current_lang:
            st.session_state["dashboard_lang"] = language_choice
            if hasattr(st, "query_params"):
                st.query_params["lang"] = language_choice
            st.rerun()

        lang = st.session_state["dashboard_lang"]
        text = UI_TEXT[lang]
        metric_labels = METRIC_LABELS[lang]

        st.header(text["data_source"])
        source = "MariaDB"
        st.caption("MariaDB")
        # SQLite support is intentionally kept in the code path, but hidden from
        # the default UI. Re-enable this selector if SQLite dashboard access is
        # needed again.
        # source = st.radio(text["source"], ["MariaDB", "SQLite"], horizontal=True)

        range_options = list(RANGES.keys())
        if "dashboard_range_name" not in st.session_state:
            query_range = get_query_param("range")
            st.session_state["dashboard_range_name"] = (
                query_range if query_range in RANGES else get_dashboard_default_range()
            )

        range_name = st.session_state["dashboard_range_name"]

        dashboard_max_points = get_dashboard_max_points()
        min_bucket_seconds = get_min_bucket_seconds_for_range(
            range_name=range_name,
            display_timezone=display_timezone,
            max_points=dashboard_max_points,
        )
        bucket_options = [
            bucket for bucket in BUCKET_SECONDS if bucket >= min_bucket_seconds
        ]

        if "dashboard_bucket_seconds" not in st.session_state:
            query_bucket_seconds = get_query_param("bucket")
            default_bucket_seconds = 600
            if query_bucket_seconds is not None:
                try:
                    parsed_bucket_seconds = int(query_bucket_seconds)
                except ValueError:
                    parsed_bucket_seconds = 600
                if parsed_bucket_seconds in bucket_options:
                    default_bucket_seconds = parsed_bucket_seconds
            if default_bucket_seconds < min_bucket_seconds:
                default_bucket_seconds = min_bucket_seconds
            st.session_state["dashboard_bucket_seconds"] = default_bucket_seconds

        if st.session_state["dashboard_bucket_seconds"] < min_bucket_seconds:
            st.session_state["dashboard_bucket_seconds"] = min_bucket_seconds

        bucket_seconds = st.selectbox(
            text["bucket_minutes"],
            bucket_options,
            key="dashboard_bucket_seconds",
            format_func=lambda value: BUCKET_LABELS[lang][value],
        )

        range_name = st.selectbox(
            text["range"],
            range_options,
            key="dashboard_range_name",
            format_func=lambda value: RANGE_LABELS[lang][value],
        )

        limit = dashboard_max_points
        st.caption(
            text["aggregate_caption"].format(
                bucket=BUCKET_LABELS[lang][bucket_seconds],
            )
        )

        if "dashboard_refresh_seconds" not in st.session_state:
            default_refresh_seconds = get_dashboard_auto_refresh_seconds()
            query_refresh_seconds = get_query_param("refresh")
            if query_refresh_seconds is not None:
                try:
                    parsed_refresh_seconds = int(query_refresh_seconds)
                except ValueError:
                    parsed_refresh_seconds = default_refresh_seconds
                if parsed_refresh_seconds in REFRESH_SECONDS:
                    default_refresh_seconds = parsed_refresh_seconds
            st.session_state["dashboard_refresh_seconds"] = default_refresh_seconds

        refresh_seconds = st.selectbox(
            text["auto_refresh"],
            REFRESH_SECONDS,
            key="dashboard_refresh_seconds",
            format_func=lambda value: REFRESH_LABELS[lang][value],
        )

        if "dashboard_axis_mode" not in st.session_state:
            query_axis_mode = get_query_param("axis")
            default_axis_mode = get_dashboard_time_axis_mode()
            if query_axis_mode in {"fixed", "auto"}:
                default_axis_mode = query_axis_mode
            st.session_state["dashboard_axis_mode"] = default_axis_mode

        axis_mode = st.selectbox(
            text["x_axis_mode"],
            ["fixed", "auto"],
            key="dashboard_axis_mode",
            format_func=lambda value: text[f"x_axis_mode_{value}"],
        )
        fixed_time_axis = axis_mode == "fixed"

        if hasattr(st, "query_params"):
            desired_query_params = {
                "lang": lang,
                "range": range_name,
                "bucket": str(bucket_seconds),
                "refresh": str(refresh_seconds),
                "axis": axis_mode,
            }
            current_managed_query_params = {
                key: get_query_param(key) for key in desired_query_params
            }
            if current_managed_query_params != desired_query_params:
                merged_query_params: dict[str, str] = {}
                if hasattr(st.query_params, "to_dict"):
                    existing_query_params = st.query_params.to_dict()
                    for key, value in existing_query_params.items():
                        if key in desired_query_params:
                            continue
                        if isinstance(value, list):
                            merged_query_params[key] = str(value[0]) if value else ""
                        else:
                            merged_query_params[key] = str(value)

                merged_query_params.update(desired_query_params)
                if hasattr(st.query_params, "from_dict"):
                    st.query_params.from_dict(merged_query_params)
                else:
                    for key, value in merged_query_params.items():
                        st.query_params[key] = value

        render_dashboard_logout(st, text)

    if hasattr(st, "fragment"):
        run_every = f"{refresh_seconds}s" if refresh_seconds > 0 else None

        @st.fragment(run_every=run_every)
        def dashboard_fragment() -> None:
            if not require_dashboard_auth(st, text):
                return

            render_dashboard_body(
                st=st,
                source=source,
                range_name=range_name,
                bucket_seconds=bucket_seconds,
                limit=int(limit),
                text=text,
                metric_labels=metric_labels,
                lang=lang,
                dashboard_title=dashboard_title,
                display_timezone=display_timezone,
                fixed_time_axis=fixed_time_axis,
            )

        dashboard_fragment()
        return

    render_dashboard_body(
        st=st,
        source=source,
        range_name=range_name,
        bucket_seconds=bucket_seconds,
        limit=int(limit),
        text=text,
        metric_labels=metric_labels,
        lang=lang,
        dashboard_title=dashboard_title,
        display_timezone=display_timezone,
        fixed_time_axis=fixed_time_axis,
    )


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"solar-rs485-monitor-dashboard {get_version()}")
        return

    if "--hash-password" in sys.argv[1:]:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            raise SystemExit("Passwords do not match")
        if not password:
            raise SystemExit("Password must not be empty")
        print(hash_dashboard_password(password))
        return

    load_config()
    cli_args = sys.argv[1:]

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        *build_streamlit_args(cli_args),
        *cli_args,
        str(Path(__file__).resolve()),
    ]
    stcli.main()


if __name__ == "__main__":
    run_app()
