import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound


SHEET_HEADERS = [
    "timestamp",
    "inverter_name",
    "inverter_id",
    "input_dc_voltage_v",
    "input_dc_current_a",
    "input_dc_power_w",
    "output_ac_voltage_v",
    "output_ac_current_a",
    "output_ac_power_w",
    "output_ac_power_factor_pct",
    "output_ac_frequency_hz",
    "total_generation_kwh",
    "fault_code",
]

_google_client = None
_google_spreadsheet = None
_cached_spreadsheet_name = None
_cached_worksheet_name = None
_cached_worksheet = None
_cached_yearly_ensure_key = None


def get_google_sheet_file_name() -> str:
    file_name = os.getenv("GOOGLE_SHEET_FILE_NAME", "").strip()

    if file_name:
        return file_name

    raise RuntimeError("GOOGLE_SHEET_FILE_NAME is not set")


def get_google_credentials_dict() -> dict:
    private_key = os.getenv("GOOGLE_PRIVATE_KEY")

    if not private_key:
        raise RuntimeError("GOOGLE_PRIVATE_KEY is not set")

    return {
        "type": os.getenv("GOOGLE_TYPE", "service_account"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key.replace("\\n", "\n"),
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv(
            "GOOGLE_AUTH_URI",
            "https://accounts.google.com/o/oauth2/auth",
        ),
        "token_uri": os.getenv(
            "GOOGLE_TOKEN_URI",
            "https://oauth2.googleapis.com/token",
        ),
        "auth_provider_x509_cert_url": os.getenv(
            "GOOGLE_AUTH_PROVIDER_X509_CERT_URL",
            "https://www.googleapis.com/oauth2/v1/certs",
        ),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL"),
        "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN", "googleapis.com"),
    }


def ensure_sheet_headers(worksheet) -> None:
    existing_headers = worksheet.row_values(1)

    if not existing_headers:
        worksheet.append_row(SHEET_HEADERS)
        return

    # Backward compatibility: allow extra trailing columns in older user sheets
    # as long as the expected headers match from the first column.
    expected_len = len(SHEET_HEADERS)
    if existing_headers[:expected_len] != SHEET_HEADERS:
        raise RuntimeError(
            "Google Sheet header mismatch. "
            "Please check row 1 manually. "
            f"expected={SHEET_HEADERS}, actual={existing_headers}"
        )


def resolve_reference_time(reference_time: datetime | None = None) -> datetime:
    ts = reference_time or datetime.now(timezone.utc)

    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)

    return ts.astimezone(timezone.utc)


def resolve_spreadsheet_name(reference_time: datetime | None = None) -> str:
    base_name = get_google_sheet_file_name()
    ts = resolve_reference_time(reference_time)

    if "%" in base_name:
        return ts.strftime(base_name)

    return f"{base_name}-{ts.year}"


def resolve_worksheet_name(reference_time: datetime | None = None) -> str:
    ts = resolve_reference_time(reference_time)
    return f"{ts.year}-{ts.month:02d}"


def get_google_client():
    global _google_client

    if _google_client is not None:
        return _google_client

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        get_google_credentials_dict(),
        scopes=scopes,
    )

    _google_client = gspread.authorize(creds)
    return _google_client


def get_google_spreadsheet(client, reference_time: datetime | None = None):
    global _google_spreadsheet
    global _cached_spreadsheet_name

    spreadsheet_name = resolve_spreadsheet_name(reference_time)

    if _google_spreadsheet is not None and _cached_spreadsheet_name == spreadsheet_name:
        return _google_spreadsheet

    try:
        _google_spreadsheet = client.open(spreadsheet_name)
    except SpreadsheetNotFound:
        _google_spreadsheet = client.create(spreadsheet_name)

    _cached_spreadsheet_name = spreadsheet_name

    return _google_spreadsheet


def ensure_yearly_monthly_worksheets(
    spreadsheet,
    year: int,
    current_month_name: str,
):
    monthly_titles = [f"{year}-{month:02d}" for month in range(1, 13)]
    worksheet_cache = {}

    try:
        worksheets = spreadsheet.worksheets()
    except APIError:
        worksheets = []

    for worksheet in worksheets:
        worksheet_cache[worksheet.title] = worksheet

    current_worksheet = None

    for title in monthly_titles:
        worksheet = worksheet_cache.get(title)

        if worksheet is None:
            worksheet = spreadsheet.add_worksheet(
                title=title,
                rows=1000,
                cols=max(20, len(SHEET_HEADERS)),
            )

        ensure_sheet_headers(worksheet)

        if title == current_month_name:
            current_worksheet = worksheet

    if current_worksheet is None:
        raise RuntimeError(f"Failed to resolve Google worksheet: {current_month_name}")

    return current_worksheet


def get_google_sheet(reference_time: datetime | None = None):
    global _cached_worksheet
    global _cached_worksheet_name
    global _cached_yearly_ensure_key

    ts = resolve_reference_time(reference_time)
    worksheet_name = resolve_worksheet_name(reference_time)
    spreadsheet_name = resolve_spreadsheet_name(reference_time)
    yearly_ensure_key = f"{spreadsheet_name}:{ts.year}"

    if (
        _cached_worksheet is not None
        and _cached_worksheet_name == worksheet_name
        and _cached_yearly_ensure_key == yearly_ensure_key
    ):
        return _cached_worksheet

    try:
        client = get_google_client()
        spreadsheet = get_google_spreadsheet(client, ts)
        worksheet = ensure_yearly_monthly_worksheets(
            spreadsheet=spreadsheet,
            year=ts.year,
            current_month_name=worksheet_name,
        )
        _cached_worksheet = worksheet
        _cached_worksheet_name = worksheet_name
        _cached_yearly_ensure_key = yearly_ensure_key
        return worksheet

    except APIError as e:
        raise RuntimeError(f"Google Sheets API error. {e}")


def write_to_google_sheet(worksheet, data: dict) -> None:
    worksheet.append_row([
        data["@timestamp"],
        data["inverter_name"],
        data["inverter_id"],
        data["input_dc_voltage_v"],
        data["input_dc_current_a"],
        data["input_dc_power_w"],
        data["output_ac_voltage_v"],
        data["output_ac_current_a"],
        data["output_ac_power_w"],
        data["output_ac_power_factor_pct"],
        data["output_ac_frequency_hz"],
        data["total_generation_kwh"],
        data["fault_code"],
    ])
