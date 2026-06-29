# Solar-RS485-Monitor

RS485/시리얼 통신으로 태양광 인버터 데이터를 수집하는 모니터링 스크립트입니다.

수집기는 인버터 데이터를 읽고, 파싱된 결과를 JSON으로 출력하며, 선택적으로 Google Sheets에 행을 추가할 수 있습니다.

## 지원 인버터 범위

현재 코드는 InoElectric IEPVS-3.5-G1/G2 인버터 기준으로 작성 및 동작 테스트되었습니다.

요청 프레임, 응답 프레임 길이, 데이터 오프셋, 스케일링 규칙, CRC 순서, 메트릭 해석은 제품별로 다릅니다. 다른 인버터 모델을 사용하는 경우 먼저 해당 제품의 명세서나 매뉴얼을 확인한 뒤, 프로토콜 처리의 송신/수신 양쪽을 모두 제품에 맞게 수정해야 합니다.

- 요청 프레임: 제품별 요청 프레임에 맞게 `INVERTER_REQUEST_HEX`를 설정합니다. 사용하는 환경이나 문서에서 이를 TCP header 또는 protocol header라고 부른다면, 해당 제품별 헤더/요청 바이트를 이 값에 포함해서 다룹니다.
- 응답 검증: 제품 응답 형식에 맞게 `INVERTER_FRAME_LENGTH`, `INVERTER_DATA_LENGTH`, `INVERTER_CRC_ORDER`, `INVERTER_ID`를 설정합니다.
- 응답 파싱: 제품이 다른 바이트 오프셋, 다른 단위, 다른 스케일링으로 필드를 반환한다면 [inverter_collector.py](/root/Workspace-RL8/Solar-RS485-Monitor/inverter_collector.py:104)의 `parse_frame()`을 수정합니다.

시리얼/TCP 연결이 성공했다고 해서 다른 RS485 인버터가 동일한 데이터 구조를 제공한다고 가정하면 안 됩니다.

## 현재 연결 방식

시리얼 연결은 `.env`의 `SERIAL_PORT`로 설정합니다.

두 가지 방식을 지원합니다.

1. 로컬 USB RS485 어댑터
2. `socat`을 사용해 원격 RS485 호스트에 장착된 RS485 USB 어댑터에 TCP로 접근

내부적으로 코드는 `pyserial`의 `serial_for_url()`을 사용하므로, 일반 장치 경로와 pyserial URL을 같은 설정값으로 처리할 수 있습니다.

## 설정

템플릿에서 `.env`를 생성합니다.

```bash
cp .env.template .env
```

의존성을 설치합니다. `uv`와 프로젝트 `.venv`를 사용하는 경우:

```bash
uv venv --python 3.14 .venv
uv pip install -r requirements.txt
```

가상환경의 Python으로 실행합니다.

```bash
.venv/bin/python inverter_collector.py
```

## 시리얼 설정

`.env`를 수정해서 `SERIAL_PORT` 한 줄만 활성화합니다.

USB를 직접 사용하는 경우:

```env
SERIAL_PORT="/dev/ttyUSB0"
#SERIAL_PORT="socket://192.168.35.6:9600"
```

현재 개발 구성처럼 RS485 USB 어댑터가 원격 RS485 호스트에 장착되어 있고 WSL에서 TCP로 접속하는 경우:

```env
#SERIAL_PORT="/dev/ttyUSB0"
SERIAL_PORT="socket://192.168.35.6:9600"
```

두 줄을 파일에 함께 남겨둘 수는 있지만, 주석 해제된 줄은 반드시 하나여야 합니다. 둘 다 주석 해제되어 있으면 마지막으로 파싱된 값이 적용될 수 있어 실제 연결 대상이 불명확해집니다.

기타 시리얼 설정:

```env
SERIAL_BAUDRATE="9600"
SERIAL_TIMEOUT="1.0"
```

## 원격 RS485 호스트 TCP 포워딩

이 프로젝트 구성에서 원격 RS485 호스트는 인버터 RS485 USB 컨버터가 물리적으로 연결된 장비입니다. VS Code와 개발 작업이 WSL에서 실행될 수 있으므로, 해당 호스트에서 `/dev/ttyUSB0`을 `socat`으로 TCP 포워딩합니다.

```bash
/usr/bin/socat TCP-LISTEN:9600,reuseaddr,fork FILE:/dev/ttyUSB0,raw,echo=0
```

그 다음 WSL 개발 환경의 `.env`에 다음처럼 설정합니다.

```env
SERIAL_PORT="socket://RS485_HOST_IP:9600"
```

예시:

```env
SERIAL_PORT="socket://192.168.35.6:9600"
```

TCP 연결에서 인버터가 응답하지 않는다면 원격 RS485 호스트의 시리얼 장치 속도도 확인해야 합니다. 어댑터와 OS 설정에 따라 `socat`의 파일 옵션에 baud rate를 포함해야 할 수 있습니다.

```bash
/usr/bin/socat TCP-LISTEN:9600,reuseaddr,fork FILE:/dev/ttyUSB0,raw,echo=0,b9600
```

## 인버터 프로토콜 설정

인버터 요청과 예상 응답 형식도 `.env`에서 설정합니다.

```env
INVERTER_NAME="YOUR_INVERTER_NAME"
INVERTER_ID="1"
INVERTER_REQUEST_HEX="7e0101d188"
INVERTER_FRAME_LENGTH="33"
INVERTER_DATA_LENGTH="26"
INVERTER_CRC_ORDER="LH"
```

`INVERTER_VERIFY_CRC`는 선택 항목이며 기본값은 `true`입니다.

```env
INVERTER_VERIFY_CRC="true"
```

## 실행

한 번 수집하고 JSON을 출력합니다.

```bash
.venv/bin/python inverter_collector.py
```

명령행에서 포트를 임시로 덮어씁니다.

```bash
.venv/bin/python inverter_collector.py --port socket://192.168.35.6:9600
```

60초마다 반복 수집합니다.

```bash
.venv/bin/python inverter_collector.py --interval 60
```

수집한 행을 Google Sheets에 기록합니다.

```bash
.venv/bin/python inverter_collector.py --google-sheet
```

반복 수집하면서 Google Sheets에 기록합니다.

```bash
.venv/bin/python inverter_collector.py --interval 60 --google-sheet
```

## Google Sheets 설정

`--google-sheet`를 사용하려면 `.env`에 다음 값을 설정합니다.

```env
GOOGLE_SHEET_NAME="YOUR_GOOGLE_SHEET_FILE_NAME"
GOOGLE_WORKSHEET_NAME="YOUR_GOOGLE_SHEET_NAME"
```

또한 `.env.template`에 있는 Google 서비스 계정 필드도 입력해야 합니다.

스프레드시트는 서비스 계정 이메일에 공유되어 있어야 합니다.

```env
GOOGLE_CLIENT_EMAIL="service-account@your-project-id.iam.gserviceaccount.com"
```

워크시트가 비어 있으면 수집기가 헤더 행을 자동 생성합니다. 1행이 이미 존재하고 예상 스키마와 다르면 헤더 불일치 오류와 함께 스크립트가 중단됩니다.

## 출력

스크립트는 수집 시도마다 JSON 객체 하나를 출력합니다.

## 수집 메트릭

InoElectric IEPVS-3.5-G1/G2 기준으로 현재 파서는 응답 데이터 페이로드를 아래처럼 해석합니다. 멀티바이트 값은 big-endian unsigned integer로 디코딩합니다.

| 출력 필드 | 데이터 바이트 | 스케일 | 단위 | 설명 |
| --- | ---: | ---: | --- | --- |
| `@timestamp` | N/A | N/A | ISO 8601 UTC | 수집기가 생성한 수집 시각 |
| `inverter_name` | N/A | N/A | text | `INVERTER_NAME` 값 |
| `inverter_id` | frame byte 1 | 1 | numeric ID | 장치가 반환한 인버터 ID |
| `pv_voltage_v` | data 0-1 | 1 | V | PV 입력 전압 |
| `pv_current_a` | data 2-3 | 1 | A | PV 입력 전류 |
| `pv_power_w` | data 4-5 | 1 | W | PV 입력 전력 |
| `grid_voltage_v` | data 6-7 | 1 | V | 계통 전압 |
| `grid_current_a` | data 8-9 | 1 | A | 계통 전류 |
| `current_output_w` | data 10-11 | 1 | W | 현재 AC 출력 전력 |
| `power_factor_pct` | data 12-13 | 0.1 | % | 역률 백분율 |
| `frequency_hz` | data 14-15 | 0.1 | Hz | 계통 주파수 |
| `total_generation_kwh` | data 16-23 | 0.001 | kWh | 누적 발전량 |
| `fault_code` | data 24-25 | 1 | code | 원시 fault 코드 |
| `fault` | `fault_code`에서 파생 | N/A | boolean | `fault_code != 0`이면 `true` |
| `raw_frame_hex` | full frame | N/A | hex bytes | 디버깅용 원시 응답 프레임 |

성공한 읽기 결과 예시:

```json
{
  "@timestamp": "2026-06-29T00:00:00+00:00",
  "inverter_name": "YOUR_INVERTER_NAME",
  "inverter_id": 1,
  "pv_voltage_v": 0,
  "pv_current_a": 0,
  "pv_power_w": 0,
  "grid_voltage_v": 0,
  "grid_current_a": 0,
  "current_output_w": 0,
  "power_factor_pct": 0.0,
  "frequency_hz": 0.0,
  "total_generation_kwh": 0.0,
  "fault_code": 0,
  "fault": false,
  "raw_frame_hex": "..."
}
```

오류도 JSON으로 출력됩니다.

```json
{
  "@timestamp": "2026-06-29T00:00:00+00:00",
  "inverter_name": "YOUR_INVERTER_NAME",
  "error": "No response from inverter"
}
```

## 문제 해결

- `No response from inverter`: `SERIAL_PORT`, 원격 RS485 호스트 IP, TCP 포트, RS485 배선, 인버터 ID, baud rate를 확인합니다.
- `Connection refused`: `socat`이 실행 중이 아니거나, IP/포트가 틀렸거나, 방화벽이 접근을 막고 있을 수 있습니다.
- `CRC mismatch`: `INVERTER_CRC_ORDER`, 요청 바이트, 예상 프레임 길이가 실제 인버터 응답과 맞는지 확인합니다.
- `Google Sheet not found or access denied`: 스프레드시트를 `GOOGLE_CLIENT_EMAIL`에 공유합니다.
- `Google worksheet not found`: 워크시트 탭을 만들거나 `GOOGLE_WORKSHEET_NAME`을 수정합니다.
