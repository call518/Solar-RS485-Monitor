import serial
import time

PORT = "/dev/ttyUSB0"
SLAVE_ID = 0x01

BAUDRATES = [9600, 19200, 38400, 4800, 115200]


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_requests():
    base = bytes([0x7E, SLAVE_ID, 0x01])
    crc = crc16_modbus(base)

    return [
        # 매뉴얼 표기: CRC High, CRC Low
        base + bytes([(crc >> 8) & 0xFF, crc & 0xFF]),

        # Modbus 일반 순서: CRC Low, CRC High
        base + bytes([crc & 0xFF, (crc >> 8) & 0xFF]),
    ]


def try_once(baudrate: int):
    print(f"\n=== baudrate={baudrate} ===")

    with serial.Serial(
        port=PORT,
        baudrate=baudrate,
        bytesize=8,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2,
    ) as ser:
        for req in build_requests():
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            print("TX:", req.hex(" "))
            ser.write(req)
            ser.flush()

            time.sleep(0.5)
            rx = ser.read(128)

            if rx:
                print("RX:", rx.hex(" "))
            else:
                print("RX: no response")


for baud in BAUDRATES:
    try:
        try_once(baud)
    except Exception as e:
        print(f"error at {baud}: {e}")
