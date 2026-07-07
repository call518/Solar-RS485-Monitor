from solar_rs485_monitor.alerts import telegram


def make_data(fault_code: int) -> dict:
    return {
        "@timestamp": "2026-07-08T06:00:00+09:00",
        "inverter_name": "Inoelectric IEPVS-3.5-G1",
        "inverter_id": 1,
        "fault_code": fault_code,
    }


def make_config() -> dict:
    return {
        "chat_ids": ["123"],
        "send_fault_event": True,
        "send_standby_event": True,
        "send_summary": False,
    }


def test_standby_and_normal_transitions_send_operation_events(monkeypatch) -> None:
    sent_messages = []

    def fake_send_to_all_chat_ids(config: dict, text: str) -> dict:
        sent_messages.append(text)
        return {
            "sent": [{"chat_id": "123", "message_id": len(sent_messages)}],
            "failed": [],
        }

    monkeypatch.setattr(telegram, "_last_operation_stopped", None)
    monkeypatch.setattr(telegram, "send_to_all_chat_ids", fake_send_to_all_chat_ids)

    first_result = telegram.write_to_telegram(make_data(0), make_config())
    standby_result = telegram.write_to_telegram(make_data(1), make_config())
    duplicate_standby_result = telegram.write_to_telegram(make_data(1), make_config())
    normal_result = telegram.write_to_telegram(make_data(0), make_config())

    assert first_result["skipped"] is True
    assert standby_result["skipped"] is False
    assert duplicate_standby_result["skipped"] is True
    assert normal_result["skipped"] is False
    assert len(sent_messages) == 2
    assert "Solar RS485 Standby Event" in sent_messages[0]
    assert "State: `STANDBY (Bit 0 = 1)`" in sent_messages[0]
    assert "Solar RS485 Normal Event" in sent_messages[1]
    assert "State: `NORMAL (Bit 0 = 0)`" in sent_messages[1]


def test_standby_to_fault_does_not_send_normal_event(monkeypatch) -> None:
    sent_messages = []

    def fake_send_to_all_chat_ids(config: dict, text: str) -> dict:
        sent_messages.append(text)
        return {
            "sent": [{"chat_id": "123", "message_id": len(sent_messages)}],
            "failed": [],
        }

    monkeypatch.setattr(telegram, "_last_operation_stopped", None)
    monkeypatch.setattr(telegram, "send_to_all_chat_ids", fake_send_to_all_chat_ids)

    telegram.write_to_telegram(make_data(1), make_config())
    fault_result = telegram.write_to_telegram(make_data(2), make_config())

    assert fault_result["skipped"] is False
    assert len(sent_messages) == 1
    assert "Solar RS485 Fault Event" in sent_messages[0]
    assert "Solar RS485 Normal Event" not in sent_messages[0]
