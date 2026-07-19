"""Inoelectric IEPVS G1/G2 인버터 응답 프레임 파서.

이 파일은 제품별 RS485 프로토콜을 실제 모니터링 데이터로 변환하는 핵심
구현이다. 다른 제품 프로토콜을 추가할 때도 보통 아래 흐름을 따른다.

1. 프레임 길이, 시작 바이트, 장치 ID, 명령, 데이터 길이를 검증한다.
2. 필요하면 CRC를 계산해 수신 프레임의 CRC와 비교한다.
3. 데이터 영역의 고정 오프셋에서 값을 읽고, 제품 매뉴얼 단위에 맞게 보정한다.
4. collector/sink 계층이 공통으로 사용할 dict 형태로 반환한다.
"""

from solar_rs485_monitor.protocols.base import InverterProtocol


def u16(data: bytes, offset: int) -> int:
    """데이터 영역에서 2바이트 unsigned 정수를 big-endian으로 읽는다.

    IEPVS 응답 데이터의 일반 계측값은 대부분 2바이트 단위로 배치된다.
    offset은 전체 프레임 기준이 아니라 `frame[5:5 + data_len]`으로 잘라낸
    데이터 영역 기준 위치다.
    """
    return int.from_bytes(data[offset:offset + 2], "big")


def u64(data: bytes, offset: int) -> int:
    """데이터 영역에서 8바이트 unsigned 정수를 big-endian으로 읽는다.

    누적 발전량처럼 2바이트로 표현하기 어려운 큰 값에 사용한다. 이 제품의
    누적 발전량은 16번 오프셋에서 8바이트로 제공된다.
    """
    return int.from_bytes(data[offset:offset + 8], "big")


def crc16(data: bytes) -> int:
    """Modbus 계열 CRC-16 값을 계산한다.

    수신 프레임의 마지막 2바이트는 CRC 자체이므로 호출자는 보통
    `frame[:-2]`만 넘긴다. 다항식은 0xA001, 초기값은 0xFFFF를 사용한다.
    """
    crc = 0xFFFF

    # 각 바이트를 하위 바이트부터 CRC 레지스터에 반영한다.
    for byte in data:
        crc ^= byte

        # CRC-16은 바이트당 8번 시프트한다. 최하위 비트가 1이면 다항식을
        # XOR하고, 0이면 단순 우측 시프트만 수행한다.
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1

    # 파이썬 int는 크기 제한이 없으므로 하위 16비트만 CRC 값으로 사용한다.
    return crc & 0xFFFF


def get_crc_from_frame(frame: bytes, crc_order: str) -> int:
    """프레임 끝의 CRC 2바이트를 설정된 바이트 순서에 맞게 정수로 변환한다."""
    # IEPVS 기본값은 LH다. 장비/문서에 따라 CRC 표기 순서가 다를 수 있어
    # 설정값으로 분기한다.
    crc_bytes = frame[-2:]

    if crc_order == "LH":
        # Low byte, High byte 순서: Modbus RTU에서 흔히 보이는 wire format이다.
        return crc_bytes[0] | (crc_bytes[1] << 8)

    if crc_order == "HL":
        # High byte, Low byte 순서: 일부 매뉴얼/캡처 도구가 이 순서로 제공한다.
        return (crc_bytes[0] << 8) | crc_bytes[1]

    # 설정 오류는 프레임 문제가 아니므로 즉시 명확한 에러로 중단한다.
    raise RuntimeError(f"Invalid INVERTER_CRC_ORDER: {crc_order}")


def parse_frame(
    frame: bytes,
    inverter_name: str,
    expected_inverter_id: int,
    expected_frame_len: int,
    expected_data_len: int,
    crc_order: str,
    verify_crc: bool,
) -> dict:
    """IEPVS 응답 프레임을 검증하고 공통 계측 dict로 변환한다.

    frame 구조:
    - 0: SOP, 항상 0x7E
    - 1: inverter_id
    - 2: command, 계측 응답은 0x02
    - 3..4: data_len, big-endian 2바이트
    - 5..(5 + data_len - 1): 계측 데이터 영역
    - 마지막 2바이트: CRC

    expected_* 값들은 환경설정/프로토콜 기본값에서 들어오며, 한 코드베이스에서
    여러 인버터 ID나 변형 프레임을 다룰 때 잘못된 데이터를 조기에 걸러낸다.
    """
    # 길이가 부족하면 이후 인덱싱에서 의미 없는 값이 나오므로 가장 먼저
    # 검사한다. raw hex를 같이 남겨 현장 캡처와 비교하기 쉽게 한다.
    if len(frame) < expected_frame_len:
        raise RuntimeError(
            f"Incomplete frame: {len(frame)} bytes "
            f"raw_frame_hex={frame.hex(' ')}"
        )

    # CRC는 통신 중 비트 오류나 프레임 경계 오인식을 잡는 최종 무결성 검사다.
    # 현장 장비가 문서와 다른 CRC를 내보내는 경우 진단을 위해 끌 수 있다.
    if verify_crc:
        received_crc = get_crc_from_frame(frame, crc_order)
        calculated_crc = crc16(frame[:-2])

        if received_crc != calculated_crc:
            raise RuntimeError(
                "CRC mismatch "
                f"received=0x{received_crc:04x} "
                f"calculated=0x{calculated_crc:04x} "
                f"frame_len={len(frame)} "
                f"raw_frame_hex={frame.hex(' ')}"
            )

    # SOP(Start Of Packet)는 이 프로토콜 프레임의 시작을 나타내는 고정 바이트다.
    if frame[0] != 0x7E:
        raise RuntimeError(
            f"Invalid SOP: 0x{frame[0]:02x} "
            f"raw_frame_hex={frame.hex(' ')}"
        )

    # 헤더 필드를 먼저 분리해 이후 검증과 데이터 영역 추출에 사용한다.
    inverter_id = frame[1]
    command = frame[2]
    data_len = int.from_bytes(frame[3:5], "big")

    # 요청한 인버터 ID와 응답 ID가 다르면 RS485 버스의 다른 장비 응답일 수 있다.
    if inverter_id != expected_inverter_id:
        raise RuntimeError(f"Unexpected inverter_id: {inverter_id}")

    # 이 파서는 계측 데이터 응답(0x02)만 해석한다. 다른 명령 응답은 별도 파서가
    # 필요하다.
    if command != 0x02:
        raise RuntimeError(f"Unexpected command: 0x{command:02x}")

    # 데이터 길이가 맞아야 아래 고정 오프셋 매핑이 올바르게 동작한다.
    if data_len != expected_data_len:
        raise RuntimeError(f"Unexpected data length: {data_len}")

    # 헤더 5바이트를 제외한 순수 데이터 영역이다. 아래 오프셋은 모두 이 slice
    # 기준으로 계산한다.
    data = frame[5:5 + data_len]

    # fault_code는 반환 dict에도 넣지만, 알람/상태 판단에서 자주 쓰일 수 있어
    # 명시적으로 먼저 읽어 이름을 붙인다.
    fault_code = u16(data, 24)

    return {
        # 운영자가 설정한 이름을 결과에 포함해 여러 대 수집 시 식별성을 유지한다.
        "inverter_name": inverter_name,
        "inverter_id": inverter_id,
        # 0..1: 입력 DC 전압. 매뉴얼상 V 단위 그대로 제공된다.
        "input_dc_voltage_v": u16(data, 0),
        # 2..3: 입력 DC 전류. 매뉴얼상 A 단위 그대로 제공된다.
        "input_dc_current_a": u16(data, 2),
        # 4..5: 입력 DC 전력. 매뉴얼상 W 단위 그대로 제공된다.
        "input_dc_power_w": u16(data, 4),
        # 6..7: 출력 AC 전압. 매뉴얼상 V 단위 그대로 제공된다.
        "output_ac_voltage_v": u16(data, 6),
        # 8..9: 출력 AC 전류. 매뉴얼상 A 단위 그대로 제공된다.
        "output_ac_current_a": u16(data, 8),
        # 10..11: 출력 AC 전력. 매뉴얼상 W 단위 그대로 제공된다.
        "output_ac_power_w": u16(data, 10),
        # 12..13: 역률은 0.1% 단위 정수로 오므로 10으로 나눠 %로 변환한다.
        "output_ac_power_factor_pct": u16(data, 12) / 10.0,
        # 14..15: 주파수는 0.1Hz 단위 정수로 오므로 10으로 나눠 Hz로 변환한다.
        "output_ac_frequency_hz": u16(data, 14) / 10.0,
        # 16..23: 누적 발전량은 Wh 단위 누적값으로 보고 kWh로 변환한다.
        "total_generation_kwh": u64(data, 16) / 1000.0,
        # 24..25: 제품별 장애/상태 코드. 의미 해석은 별도 매핑이 필요하다.
        "fault_code": fault_code,
        # 원본 프레임은 장애 분석과 신규 프로토콜 작성 시 기준 샘플로 유용하다.
        "raw_frame_hex": frame.hex(" "),
    }


# 프로토콜 레지스트리에 등록되는 제품 프로파일이다. collector는 사용자가 지정한
# INVERTER_PROTOCOL 이름/alias로 이 객체를 찾고, 기본 요청 프레임과 파서를 사용한다.
PROTOCOL = InverterProtocol(
    # canonical name. 설정, 테스트, 문서에서 기준 이름으로 사용한다.
    name="inoelectric_iepvs_g1_g2",
    # 사용자가 제품명을 조금 다르게 입력해도 같은 프로토콜로 해석하도록 한다.
    aliases=(
        "inoelectric",
        "iepvs",
        "iepvs_g1_g2",
        "inoelectric_iepvs",
        "inoelectric_iepvs_3_5_g1_g2",
    ),
    # 인버터에 계측 데이터를 요청할 때 송신하는 기본 프레임이다.
    default_request_hex="7e0101d188",
    # 전체 응답 프레임 길이: 헤더 5바이트 + 데이터 26바이트 + CRC 2바이트.
    default_frame_length=33,
    # 데이터 영역 길이. 이 값이 바뀌면 위 필드 오프셋 매핑도 재검토해야 한다.
    default_data_length=26,
    # 수신 프레임 마지막 2바이트의 CRC 저장 순서. 기본 장비 캡처는 LH다.
    default_crc_order="LH",
    # 실제 응답 프레임을 dict로 변환하는 함수 참조다.
    parse_frame=parse_frame,
)
