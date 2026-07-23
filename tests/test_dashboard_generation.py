from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from solar_rs485_monitor.dashboard import build_generation_snapshot


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
