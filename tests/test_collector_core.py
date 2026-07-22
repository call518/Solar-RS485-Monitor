import json
from datetime import datetime, timezone

import pytest

from solar_rs485_monitor import collector


class FailingThenPassingProtocol:
    name = "test"
    calls = 0

    def parse_frame(
        self,
        frame: bytes,
        inverter_name: str,
        expected_inverter_id: int,
        expected_frame_len: int,
        expected_data_len: int,
        crc_order: str,
        verify_crc: bool,
    ) -> dict:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("CRC mismatch calculated=0x0000")

        return {
            "inverter_name": inverter_name,
            "inverter_id": expected_inverter_id,
            "raw_frame_hex": frame.hex(" "),
        }


class AlwaysFailingProtocol:
    name = "test"

    def parse_frame(
        self,
        frame: bytes,
        inverter_name: str,
        expected_inverter_id: int,
        expected_frame_len: int,
        expected_data_len: int,
        crc_order: str,
        verify_crc: bool,
    ) -> dict:
        raise RuntimeError("Unexpected command: 0x03")


def test_alert_runtime_state_applies_cooldown() -> None:
    state = collector.AlertRuntimeState(cooldown_seconds=10)

    assert state.can_send("same-error", now=100.0) is True
    assert state.can_send("same-error", now=105.0) is False
    assert state.can_send("same-error", now=110.0) is True
    assert state.can_send("other-error", now=111.0) is True


def test_summarize_alert_result_counts_all_result_shapes() -> None:
    summary = collector.summarize_alert_result({
        "skipped": False,
        "chat_ids": ["1", "2"],
        "summary": {"sent": [{"message_id": 1}], "failed": []},
        "fault_event": {"sent": [], "failed": [{"chat_id": "2"}]},
        "sent": [{"message_id": 3}],
        "failed": [],
    })

    assert summary == {
        "alert_skipped": False,
        "alert_targets": 2,
        "summary_sent_count": 1,
        "summary_failed_count": 0,
        "fault_event_sent_count": 0,
        "fault_event_failed_count": 1,
        "sent_count": 1,
        "failed_count": 0,
    }


def test_log_event_writes_structured_json(capsys: pytest.CaptureFixture[str]) -> None:
    collector.log_event(
        section="[Test]",
        level="warning",
        event="unit_test_event",
        component="collector",
        action="continued",
    )

    output = capsys.readouterr().out
    assert "== [Test] ==" in output

    payload = output.split("== [Test] ==")[1].strip()
    logged = json.loads(payload)

    assert logged["level"] == "warning"
    assert logged["event"] == "unit_test_event"
    assert logged["component"] == "collector"
    assert logged["action"] == "continued"
    assert "@timestamp" in logged


def test_collector_state_file_round_trip_and_standby_detection(tmp_path) -> None:
    state_path = tmp_path / "collector-state.json"

    collector.write_collector_state(state_path, {
        "inverter_name": "Test Inverter",
        "inverter_id": 1,
        "fault_code": 1,
    })

    state = collector.read_collector_state(
        state_path,
        max_age_seconds=86400,
        now=datetime.now(timezone.utc),
    )

    assert state is not None
    assert state["fault_code"] == 1
    assert state["operation_stopped"] is True
    assert state["has_fault"] is False
    assert collector.is_standby_state(state) is True


def test_missing_collector_state_file_is_unknown_not_error(tmp_path) -> None:
    state = collector.read_collector_state(
        tmp_path / "missing-state.json",
        max_age_seconds=86400,
        now=datetime.now(timezone.utc),
    )

    assert state is None
    assert collector.is_standby_state(state) is False


def test_unknown_state_no_response_suppress_respects_grace_period() -> None:
    assert collector.should_suppress_unknown_state_no_response(
        process_started_at=100.0,
        suppress_seconds=3600.0,
        now=200.0,
    ) is True
    assert collector.should_suppress_unknown_state_no_response(
        process_started_at=100.0,
        suppress_seconds=3600.0,
        now=3700.0,
    ) is False
    assert collector.should_suppress_unknown_state_no_response(
        process_started_at=100.0,
        suppress_seconds=0.0,
        now=200.0,
    ) is False


def test_time_window_supports_cross_midnight_range() -> None:
    start = collector.parse_hhmm("20:00")
    end = collector.parse_hhmm("04:00")

    assert collector.is_time_in_window(collector.parse_hhmm("21:30"), start, end)
    assert collector.is_time_in_window(collector.parse_hhmm("03:59"), start, end)
    assert not collector.is_time_in_window(collector.parse_hhmm("12:00"), start, end)
    assert not collector.is_time_in_window(collector.parse_hhmm("04:00"), start, end)


def test_night_no_response_suppress_uses_configured_timezone() -> None:
    suppressed, context = collector.should_suppress_night_no_response(
        enabled=True,
        timezone_name="Asia/Seoul",
        start_time_text="20:00",
        end_time_text="04:00",
        now=datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc),
    )

    assert suppressed is True
    assert context["local_timezone"] == "Asia/Seoul"
    assert context["night_start"] == "20:00"
    assert context["night_end"] == "04:00"


def test_night_no_response_suppress_is_false_outside_window() -> None:
    suppressed, context = collector.should_suppress_night_no_response(
        enabled=True,
        timezone_name="Asia/Seoul",
        start_time_text="20:00",
        end_time_text="04:00",
        now=datetime(2026, 7, 22, 6, 0, tzinfo=timezone.utc),
    )

    assert suppressed is False
    assert context["local_timezone"] == "Asia/Seoul"


def test_night_no_response_suppress_raises_for_invalid_timezone() -> None:
    with pytest.raises(RuntimeError, match="Invalid COLLECTOR_LOCAL_TIMEZONE"):
        collector.should_suppress_night_no_response(
            enabled=True,
            timezone_name="Invalid/Zone",
            start_time_text="20:00",
            end_time_text="04:00",
            now=datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc),
        )


def test_expired_collector_state_file_is_unknown(tmp_path) -> None:
    state_path = tmp_path / "collector-state.json"
    state_path.write_text(
        json.dumps({
            "updated_at": "2026-07-08T00:00:00+00:00",
            "fault_code": 1,
            "operation_stopped": True,
            "has_fault": False,
        }),
        encoding="utf-8",
    )

    state = collector.read_collector_state(
        state_path,
        max_age_seconds=60,
        now=datetime(2026, 7, 8, 0, 2, tzinfo=timezone.utc),
    )

    assert state is None


def test_fault_state_does_not_count_as_standby() -> None:
    state = {
        "fault_code": 3,
        "operation_stopped": True,
        "has_fault": True,
    }

    assert collector.is_standby_state(state) is False


def test_low_output_power_derives_standby_when_bit_zero_not_seen() -> None:
    result = collector.apply_operation_state(
        data={"fault_code": 0, "output_ac_power_w": 12},
        previous_operation_stopped=False,
        standby_power_w_threshold=20,
        normal_power_w_threshold=30,
    )

    assert result["operation_stopped"] is True
    assert result["operation_state"] == "standby"
    assert result["operation_state_reason"] == "low_output_power"


def test_fault_code_bit_zero_overrides_power_fallback() -> None:
    result = collector.apply_operation_state(
        data={"fault_code": 1, "output_ac_power_w": 120},
        previous_operation_stopped=False,
        standby_power_w_threshold=20,
        normal_power_w_threshold=30,
    )

    assert result["operation_stopped"] is True
    assert result["operation_state_reason"] == "fault_code_bit_0"


def test_hysteresis_band_keeps_previous_operation_state() -> None:
    standby_result = collector.apply_operation_state(
        data={"fault_code": 0, "output_ac_power_w": 25},
        previous_operation_stopped=True,
        standby_power_w_threshold=20,
        normal_power_w_threshold=30,
    )
    normal_result = collector.apply_operation_state(
        data={"fault_code": 0, "output_ac_power_w": 25},
        previous_operation_stopped=False,
        standby_power_w_threshold=20,
        normal_power_w_threshold=30,
    )

    assert standby_result["operation_stopped"] is True
    assert standby_result["operation_state_reason"] == "hysteresis_keep_standby"
    assert normal_result["operation_stopped"] is False
    assert normal_result["operation_state_reason"] == "hysteresis_keep_normal"


def test_recovered_output_power_derives_normal() -> None:
    result = collector.apply_operation_state(
        data={"fault_code": 0, "output_ac_power_w": 35},
        previous_operation_stopped=True,
        standby_power_w_threshold=20,
        normal_power_w_threshold=30,
    )

    assert result["operation_stopped"] is False
    assert result["operation_state"] == "normal"
    assert result["operation_state_reason"] == "output_power_recovered"


def test_collector_state_uses_derived_operation_state(tmp_path) -> None:
    state_path = tmp_path / "collector-state.json"

    collector.write_collector_state(state_path, {
        "inverter_name": "Test Inverter",
        "inverter_id": 1,
        "fault_code": 0,
        "output_ac_power_w": 12,
        "operation_stopped": True,
        "operation_state": "standby",
        "operation_state_reason": "low_output_power",
    })

    state = collector.read_collector_state(
        state_path,
        max_age_seconds=86400,
        now=datetime.now(timezone.utc),
    )

    assert state is not None
    assert state["operation_stopped"] is True
    assert state["operation_state_reason"] == "low_output_power"
    assert collector.is_standby_state(state) is True


def test_collect_once_retries_retryable_parse_error(monkeypatch) -> None:
    reads = []

    def fake_read_frame(
        port: str,
        baudrate: int,
        timeout: float,
        request: bytes,
        expected_frame_len: int,
    ) -> bytes:
        reads.append((port, baudrate, timeout, request, expected_frame_len))
        return b"\x7e\x01\x02"

    monkeypatch.setattr(collector, "read_frame", fake_read_frame)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: None)

    result = collector.collect_once(
        port="/dev/null",
        baudrate=9600,
        timeout=1.0,
        request=b"\x01",
        inverter_name="Test Inverter",
        protocol=FailingThenPassingProtocol(),
        expected_inverter_id=1,
        expected_frame_len=3,
        expected_data_len=0,
        crc_order="LH",
        verify_crc=True,
        read_retries=1,
    )

    assert len(reads) == 2
    assert result["inverter_name"] == "Test Inverter"
    assert result["raw_frame_hex"] == "7e 01 02"
    assert "@timestamp" in result


def test_collect_once_does_not_retry_non_retryable_parse_error(monkeypatch) -> None:
    reads = []

    def fake_read_frame(
        port: str,
        baudrate: int,
        timeout: float,
        request: bytes,
        expected_frame_len: int,
    ) -> bytes:
        reads.append(expected_frame_len)
        return b"\x7e\x01\x03"

    monkeypatch.setattr(collector, "read_frame", fake_read_frame)

    with pytest.raises(RuntimeError, match="Unexpected command"):
        collector.collect_once(
            port="/dev/null",
            baudrate=9600,
            timeout=1.0,
            request=b"\x01",
            inverter_name="Test Inverter",
            protocol=AlwaysFailingProtocol(),
            expected_inverter_id=1,
            expected_frame_len=3,
            expected_data_len=0,
            crc_order="LH",
            verify_crc=True,
            read_retries=3,
        )

    assert reads == [3]
