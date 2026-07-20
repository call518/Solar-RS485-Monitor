import json

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
