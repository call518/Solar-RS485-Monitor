from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from solar_rs485_monitor.dashboard import (
    build_generation_snapshot,
    format_fault_event_active_bits,
    format_fault_event_code,
    format_fault_event_label,
    get_fault_code_label,
    get_fault_event_rows,
    extract_virtual_event,
    has_fault_condition,
    is_operation_stopped,
)


def test_build_generation_snapshot_includes_current_week_generation() -> None:
    daily_df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
                "value": 4.5,
            },
            {
                "timestamp": datetime(2026, 7, 21, 12, tzinfo=timezone.utc),
                "value": 5.0,
            },
            {
                "timestamp": datetime(2026, 7, 13, 12, tzinfo=timezone.utc),
                "value": 9.0,
            },
        ]
    )

    snapshot = build_generation_snapshot(
        daily_df=daily_df,
        snapshot_timestamp=datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
        display_timezone=ZoneInfo("Asia/Seoul"),
    )

    assert snapshot["weekly_generation_kwh"] == 9.5


def test_collector_virtual_event_is_rendered_without_fault_code() -> None:
    raw_frame_hex = "[V:1] 4f ab 7e 01"
    virtual_event = extract_virtual_event(raw_frame_hex)

    assert virtual_event == 1
    assert format_fault_event_code(None, virtual_event) == "-"
    assert format_fault_event_active_bits(None, virtual_event) == "가상이벤트"
    assert format_fault_event_label(None, virtual_event) == (
        "가상이벤트: 수집기 CRC 오류"
    )
    assert format_fault_event_label(None, 2) == "가상이벤트: 2"


def test_dashboard_decodes_fault_code_with_protocol_metadata() -> None:
    assert is_operation_stopped(1) is True
    assert has_fault_condition(2) is True
    assert get_fault_code_label(3) == "인버터 미작동, 태양전지 과전압"
    assert get_fault_event_rows(2, (0, 1)) == [
        "bit1 | 0x0002 | 2 | 태양전지 과전압"
    ]
