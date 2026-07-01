import html
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    "fault": "Fault (0/1)",
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
        "fault_code": "점검 코드",
        "fault": "점검 (0/1)",
    },
    "en": METRICS,
}

UI_TEXT = {
    "ko": {
        "language": "언어 / Language",
        "data_source": "데이터 소스",
        "source": "소스",
        "range": "조회 범위",
        "bucket_minutes": "집계 시간 단위",
        "max_points": "최대 조회 포인트 수",
        "aggregate_caption": (
            "이 값은 차트에 표시할 {bucket} 단위 집계 데이터의 "
            "최대 포인트 수입니다."
        ),
        "no_rows": "선택한 소스와 조회 범위에 해당하는 데이터가 없습니다.",
        "inverter": "인버터",
        "id": "ID",
        "latest": "최신 시각",
        "ac_output_w": "AC 출력 (W)",
        "fault": "점검",
        "fault_normal": "정상",
        "fault_fault": "장애",
        "metric_charts": "메트릭 차트",
        "chart_caption": "각 차트는 선택한 조회 범위의 {bucket} 단위 집계값을 표시합니다.",
        "latest_rows": "최신 데이터 (최대 200행)",
    },
    "en": {
        "language": "Language",
        "data_source": "Data Source",
        "source": "Source",
        "range": "Range",
        "bucket_minutes": "Aggregation interval",
        "max_points": "Max chart points",
        "aggregate_caption": (
            "This limits the maximum number of {bucket} aggregated chart "
            "points shown."
        ),
        "no_rows": "No rows found for the selected source and range.",
        "inverter": "Inverter",
        "id": "ID",
        "latest": "Latest",
        "ac_output_w": "AC Output (W)",
        "fault": "Fault",
        "fault_normal": "NORMAL",
        "fault_fault": "FAULT",
        "metric_charts": "Metric Charts",
        "chart_caption": "Each chart shows {bucket} aggregated values for the selected range.",
        "latest_rows": "Latest Rows (max 200)",
    },
}

RANGE_LABELS = {
    "ko": {
        "Last 1 hour": "최근 1시간",
        "Last 6 hours": "최근 6시간",
        "Last 24 hours": "최근 24시간",
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
        "Last 3 days": "Last 3 days",
        "Last 7 days": "Last 7 days",
        "Last 30 days": "Last 30 days",
        "Last 90 days": "Last 90 days",
        "Last 6 months": "Last 6 months",
    },
}

BUCKET_MINUTES = [1, 5, 10, 30]

BUCKET_LABELS = {
    "ko": {
        1: "1분",
        5: "5분",
        10: "10분",
        30: "30분",
    },
    "en": {
        1: "1 minute",
        5: "5 minutes",
        10: "10 minutes",
        30: "30 minutes",
    },
}

TABLE_LABELS = {
    "ko": {
        "timestamp": "시각 (UTC)",
        "inverter_name": "인버터 이름",
        "inverter_id": "인버터 ID",
        **METRIC_LABELS["ko"],
    },
    "en": {
        "timestamp": "Timestamp (UTC)",
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
    ["fault", "fault_code"],
]

BAR_CHART_COLORS = {
    "total_generation_kwh": "#16a34a",
    "fault": "#dc2626",
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

RANGES = {
    "Last 1 hour": timedelta(hours=1),
    "Last 6 hours": timedelta(hours=6),
    "Last 24 hours": timedelta(hours=24),
    "Last 3 days": timedelta(days=3),
    "Last 7 days": timedelta(days=7),
    "Last 30 days": timedelta(days=30),
    "Last 90 days": timedelta(days=90),
    "Last 6 months": timedelta(days=183),
}

MAX_AGGREGATE_METRICS = {
    "total_generation_kwh",
    "fault_code",
    "fault",
}


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


def get_dashboard_title() -> str:
    return (
        os.getenv("DASHBOARD_TITLE", DEFAULT_DASHBOARD_TITLE).strip()
        or DEFAULT_DASHBOARD_TITLE
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


def get_time_bounds(range_name: str) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - RANGES[range_name], now


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


def format_table_header(column: str, lang: str) -> str:
    label = TABLE_LABELS[lang].get(column, column)
    return (
        f"<th><strong>{html.escape(label)}</strong>"
        f"<br><span>({html.escape(column)})</span></th>"
    )


def render_latest_rows_table(df, columns: list[str], lang: str) -> str:
    display_df = df.sort_values("timestamp", ascending=False)[columns].head(200)
    header = "".join(format_table_header(column, lang) for column in columns)
    rows = []

    for _, row in display_df.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            if hasattr(value, "isoformat"):
                value = value.isoformat(sep=" ")
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
      }}
      table th span {{
        color: #6b7280;
        font-size: 0.75rem;
        font-weight: 400;
      }}
      table td {{
        border-bottom: 1px solid #e5e7eb;
        padding: 0.45rem 0.5rem;
        white-space: nowrap;
      }}
    </style>
    """


def render_area_chart(st, chart_df, metric_name: str, metric_label: str) -> None:
    import altair as alt

    color = AREA_CHART_COLORS.get(metric_name, "#3b82f6")
    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
    )

    base = alt.Chart(chart_data).encode(
        x=alt.X(
            "timestamp:T",
            title=None,
        ),
        y=alt.Y(
            "value:Q",
            title=metric_label,
            scale=alt.Scale(zero=False),
        ),
        tooltip=[
            alt.Tooltip("timestamp:T", title="timestamp"),
            alt.Tooltip("value:Q", title=metric_name),
        ],
    )
    area = base.mark_area(
        color=color,
        opacity=0.18,
        interpolate="monotone",
    )
    line = base.mark_line(
        color=color,
        strokeWidth=2,
        interpolate="monotone",
    )

    st.altair_chart(area + line, use_container_width=True)


def render_bar_chart(st, chart_df, metric_name: str, metric_label: str) -> None:
    import altair as alt

    color = BAR_CHART_COLORS.get(metric_name, "#16a34a")
    chart_data = (
        chart_df[[metric_name]]
        .reset_index()
        .rename(columns={metric_name: "value"})
    )

    chart = (
        alt.Chart(chart_data)
        .mark_bar(color=color)
        .encode(
            x=alt.X(
                "timestamp:T",
                title=None,
            ),
            y=alt.Y("value:Q", title=metric_label),
            tooltip=[
                alt.Tooltip("timestamp:T", title="timestamp"),
                alt.Tooltip("value:Q", title=metric_name),
            ],
        )
    )

    st.altair_chart(chart, use_container_width=True)


def validate_bucket_minutes(bucket_minutes: int) -> int:
    if bucket_minutes not in BUCKET_MINUTES:
        raise RuntimeError(f"Invalid aggregation interval: {bucket_minutes}")

    return bucket_minutes


def read_sqlite_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_minutes: int,
):
    import pandas as pd

    bucket_minutes = validate_bucket_minutes(bucket_minutes)
    bucket_seconds = bucket_minutes * 60
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

    return normalize_dataframe(df)


def read_mariadb_data(
    since: datetime,
    until: datetime,
    limit: int,
    bucket_minutes: int,
):
    import pandas as pd
    import pymysql

    bucket_minutes = validate_bucket_minutes(bucket_minutes)
    bucket_seconds = bucket_minutes * 60
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

    return normalize_dataframe(df)


def run_app() -> None:
    import streamlit as st

    load_config()
    dashboard_title = get_dashboard_title()

    st.set_page_config(
        page_title=dashboard_title,
        layout="wide",
    )

    with st.sidebar:
        language = st.selectbox(
            "언어 / Language",
            ["한국어", "English"],
            index=0,
        )
        lang = "ko" if language == "한국어" else "en"
        text = UI_TEXT[lang]
        metric_labels = METRIC_LABELS[lang]

        st.header(text["data_source"])
        source = "MariaDB"
        st.caption("MariaDB")
        # SQLite support is intentionally kept in the code path, but hidden from
        # the default UI. Re-enable this selector if SQLite dashboard access is
        # needed again.
        # source = st.radio(text["source"], ["MariaDB", "SQLite"], horizontal=True)
        range_name = st.selectbox(
            text["range"],
            list(RANGES.keys()),
            index=2,
            format_func=lambda value: RANGE_LABELS[lang][value],
        )
        bucket_minutes = st.selectbox(
            text["bucket_minutes"],
            BUCKET_MINUTES,
            index=0,
            format_func=lambda value: BUCKET_LABELS[lang][value],
        )
        limit = st.number_input(
            text["max_points"],
            min_value=100,
            max_value=300000,
            value=50000,
            step=1000,
        )
        st.caption(
            text["aggregate_caption"].format(
                bucket=BUCKET_LABELS[lang][bucket_minutes],
            )
        )

    st.title(dashboard_title)

    since, until = get_time_bounds(range_name)

    try:
        if source == "MariaDB":
            df = read_mariadb_data(
                since,
                until,
                int(limit),
                bucket_minutes,
            )
        else:
            df = read_sqlite_data(
                since,
                until,
                int(limit),
                bucket_minutes,
            )
    except Exception as e:
        st.error(str(e))
        return

    if df.empty:
        st.warning(text["no_rows"])
        return

    latest = df.sort_values("timestamp").iloc[-1]
    inverter_name = latest.get("inverter_name", "")
    inverter_id = int(latest.get("inverter_id", 0))
    fault = int(latest.get("fault", 0))
    fault_label = text["fault_fault"] if fault else text["fault_normal"]
    fault_color = "#dc2626" if fault else "#16a34a"
    fault_bg = "#fee2e2" if fault else "#dcfce7"

    st.markdown(
        f"""
        <div style="font-size: 1.1rem; line-height: 1.5; margin-bottom: 0.75rem;">
          <strong>{text["inverter"]}:</strong> {html.escape(str(inverter_name))}
          <span style="margin-left: 1.5rem;"><strong>{text["id"]}:</strong> {inverter_id}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_columns = st.columns(3)
    summary_columns[0].metric(
        text["latest"],
        str(latest["timestamp"]),
    )
    summary_columns[1].metric(text["ac_output_w"], latest.get("output_ac_power_w"))
    summary_columns[2].markdown(
        f"""
        <div style="font-size: 0.875rem; margin-bottom: 0.25rem;">{text["fault"]}</div>
        <div style="
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.65rem;
            border-radius: 0.4rem;
            color: {fault_color};
            background: {fault_bg};
            border: 1px solid {fault_color};
            font-weight: 700;
            letter-spacing: 0.02em;
        ">{fault_label} ({fault})</div>
        """,
        unsafe_allow_html=True,
    )

    chart_df = df.sort_values("timestamp").set_index("timestamp")
    st.subheader(text["metric_charts"])
    st.caption(
        text["chart_caption"].format(
            bucket=BUCKET_LABELS[lang][bucket_minutes],
        )
    )

    for group in CHART_GROUPS:
        if len(group) == 1:
            metric_name = group[0]
            st.markdown(f"#### {metric_labels[metric_name]}")
            if metric_name in BAR_CHART_COLORS:
                render_bar_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                )
            else:
                render_area_chart(
                    st,
                    chart_df,
                    metric_name,
                    metric_labels[metric_name],
                )
            continue

        chart_columns = st.columns(2)

        for column, metric_name in zip(chart_columns, group):
            with column:
                st.markdown(f"#### {metric_labels[metric_name]}")
                if metric_name in BAR_CHART_COLORS:
                    render_bar_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                    )
                else:
                    render_area_chart(
                        st,
                        chart_df,
                        metric_name,
                        metric_labels[metric_name],
                    )

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
        render_latest_rows_table(df, display_columns, lang),
        unsafe_allow_html=True,
    )


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(f"solar-rs485-monitor-dashboard {get_version()}")
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
