from solar_rs485_monitor.protocols import get_protocol, list_protocol_names


SAMPLE_FRAME = bytes.fromhex(
    "7e 01 02 00 1a 00 c1 00 00 00 36 00 e5 00 00 "
    "00 25 03 52 02 58 00 00 00 00 00 01 b6 74 00 00 7c 21"
)


def test_protocol_registry_resolves_default_profile_and_aliases() -> None:
    assert list_protocol_names() == ["inoelectric_iepvs_g1_g2"]
    assert get_protocol("inoelectric_iepvs_g1_g2").name == "inoelectric_iepvs_g1_g2"
    assert get_protocol("inoelectric").name == "inoelectric_iepvs_g1_g2"
    assert get_protocol("iepvs-g1-g2").name == "inoelectric_iepvs_g1_g2"


def test_inoelectric_iepvs_g1_g2_parses_sample_frame() -> None:
    protocol = get_protocol("inoelectric_iepvs_g1_g2")

    parsed = protocol.parse_frame(
        frame=SAMPLE_FRAME,
        inverter_name="Inoelectric IEPVS-3.5-G1",
        expected_inverter_id=1,
        expected_frame_len=33,
        expected_data_len=26,
        crc_order="LH",
        verify_crc=True,
    )

    assert parsed["inverter_name"] == "Inoelectric IEPVS-3.5-G1"
    assert parsed["inverter_id"] == 1
    assert parsed["input_dc_voltage_v"] == 193
    assert parsed["input_dc_current_a"] == 0
    assert parsed["input_dc_power_w"] == 54
    assert parsed["output_ac_voltage_v"] == 229
    assert parsed["output_ac_current_a"] == 0
    assert parsed["output_ac_power_w"] == 37
    assert parsed["output_ac_power_factor_pct"] == 85.0
    assert parsed["output_ac_frequency_hz"] == 60.0
    assert parsed["total_generation_kwh"] == 112.244
    assert parsed["fault_code"] == 0
    assert parsed["raw_frame_hex"] == SAMPLE_FRAME.hex(" ")
