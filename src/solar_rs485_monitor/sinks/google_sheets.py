import os

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound


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
    "fault",
]


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

    if existing_headers != SHEET_HEADERS:
        raise RuntimeError(
            "Google Sheet header mismatch. "
            "Please check row 1 manually. "
            f"expected={SHEET_HEADERS}, actual={existing_headers}"
        )


def get_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        get_google_credentials_dict(),
        scopes=scopes,
    )

    client = gspread.authorize(creds)

    spreadsheet_name = os.getenv("GOOGLE_SHEET_NAME")
    worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME")
    client_email = os.getenv("GOOGLE_CLIENT_EMAIL")

    if not spreadsheet_name:
        raise RuntimeError("GOOGLE_SHEET_NAME is not set")

    if not worksheet_name:
        raise RuntimeError("GOOGLE_WORKSHEET_NAME is not set")

    try:
        spreadsheet = client.open(spreadsheet_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        ensure_sheet_headers(worksheet)
        return worksheet

    except SpreadsheetNotFound:
        raise RuntimeError(
            "Google Sheet not found or access denied. "
            f"sheet_name={spreadsheet_name!r}. "
            "Check that the spreadsheet exists and is shared with "
            f"{client_email!r}."
        )

    except WorksheetNotFound:
        raise RuntimeError(
            "Google worksheet not found. "
            f"worksheet_name={worksheet_name!r}. "
            "Create the worksheet tab or check GOOGLE_WORKSHEET_NAME."
        )

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
        data["fault"],
    ])
