# Solar-RS485-Monitor

RS485/시리얼 통신으로 태양광 인버터 데이터를 수집하는 모니터링 스크립트입니다.

수집기는 인버터 데이터를 읽고, 파싱된 결과를 JSON으로 출력하며, 선택적으로 외부 로깅 sink에 기록할 수 있습니다.

선택적 로깅 sink는 `src/solar_rs485_monitor/sinks/` 아래의 별도 모듈로 구현합니다. 이렇게 해서 인버터 수집 로직과 SQLite, Google Sheets, ThingSpeak, MariaDB, OpenSearch 또는 Elasticsearch 같은 외부 로깅 연동을 분리합니다.

## 수집 데이터 요약

현재 파서를 지원되는 InoElectric IEPVS-3.5-G1/G2 인버터와 함께 사용하면, 성공한 읽기마다 아래 핵심 값들이 생성됩니다.

| 분류 | 메트릭 | 의미 |
| --- | --- | --- |
| 메타데이터 | `@timestamp` | UTC 기준 수집 시각 |
| 메타데이터 | `inverter_name` | 설정된 인버터 이름 |
| 메타데이터 | `inverter_id` | 장치가 반환한 인버터 ID |
| DC 입력 | `input_dc_voltage_v` | PV 입력 DC 전압 |
| DC 입력 | `input_dc_current_a` | PV 입력 DC 전류 |
| DC 입력 | `input_dc_power_w` | PV 입력 DC 전력 |
| AC 출력 | `output_ac_voltage_v` | 계통 연계 AC 출력 전압 |
| AC 출력 | `output_ac_current_a` | 계통 연계 AC 출력 전류 |
| AC 출력 | `output_ac_power_w` | 계통 연계 AC 출력 전력 |
| AC 출력 | `output_ac_power_factor_pct` | 계통 연계 AC 출력 역률 |
| AC 출력 | `output_ac_frequency_hz` | 계통 연계 AC 출력 주파수 |
| 발전량 | `total_generation_kwh` | 누적 발전량 |
| 상태 | `fault_code` | 원시 인버터 fault 코드 |
| 상태 | `fault` | `fault_code`에서 파생한 숫자형 고장 여부 |
| 디버그 | `raw_frame_hex` | 문제 확인용 원시 응답 프레임 |

같은 파싱 결과는 JSON으로 출력할 수 있고, 선택적으로 SQLite, Google Sheets, ThingSpeak, MariaDB, OpenSearch 또는 Elasticsearch에 기록할 수 있습니다.

## 지원 인버터 범위

현재 코드는 InoElectric IEPVS-3.5-G1/G2 인버터 기준으로 작성 및 동작 테스트되었습니다.

요청 프레임, 응답 프레임 길이, 데이터 오프셋, 스케일링 규칙, CRC 순서, 메트릭 해석은 제품별로 다릅니다. 다른 인버터 모델을 사용하는 경우 먼저 해당 제품의 명세서나 매뉴얼을 확인한 뒤, 프로토콜 처리의 송신과 수신 모두를 제품에 맞게 수정해야 합니다.

- 요청 프레임: 제품별 요청 프레임에 맞게 `INVERTER_REQUEST_HEX`를 설정합니다. 사용하는 환경이나 문서에서 이를 TCP header 또는 protocol header라고 부른다면, 해당 제품별 헤더/요청 바이트를 이 값에 포함해서 다룹니다.
- 응답 검증: 제품 응답 형식에 맞게 `INVERTER_FRAME_LENGTH`, `INVERTER_DATA_LENGTH`, `INVERTER_CRC_ORDER`, `INVERTER_ID`를 설정합니다.
- 응답 파싱: 제품이 다른 바이트 오프셋, 다른 단위, 다른 스케일링으로 필드를 반환한다면 [src/solar_rs485_monitor/collector.py](src/solar_rs485_monitor/collector.py)의 `parse_frame()`을 수정합니다.

시리얼/TCP 연결이 성공했다고 해서 다른 RS485 인버터가 동일한 데이터 구조를 제공한다고 가정하면 안 됩니다.

## 현재 연결 방식

시리얼 연결은 `solar-rs485-monitor.conf`의 `SERIAL_PORT`로 설정합니다.

두 가지 방식을 지원합니다.

1. 로컬 USB RS485 어댑터
2. `socat`을 사용해 원격 RS485 호스트에 장착된 RS485 USB 어댑터에 TCP로 접근

내부적으로 코드는 `pyserial`의 `serial_for_url()`을 사용하므로, 일반 장치 경로와 pyserial URL을 같은 설정값으로 처리할 수 있습니다.

## SQLite 빠른 시작

외부 로깅 서비스 없이 데이터를 수집하고 저장된 행을 바로 확인하는 최소 절차입니다.

1. 패키지를 설치합니다.

```bash
pip install solar-rs485-monitor
```

2. 1순위 설정 파일을 생성합니다.

```bash
solar-rs485-monitor --print-config-template > /etc/solar-rs485-monitor.conf
```

3. `/etc/solar-rs485-monitor.conf`에서 최소한 아래 값을 실제 인버터와 RS485 연결에 맞게 수정합니다.

```env
SERIAL_PORT="/dev/ttyUSB0"
INVERTER_NAME="YOUR_INVERTER_NAME"
INVERTER_ID="1"
INVERTER_REQUEST_HEX="YOUR_INVERTER_REQUEST_HEX"
SQLITE_PATH="/tmp/solar-rs485-monitor.sqlite3"
```

4. 수집을 시작하고 SQLite에 기록합니다.

```bash
solar-rs485-monitor --sqlite
```

5. 최근 데이터를 조회합니다.

```bash
sqlite3 -header -column /tmp/solar-rs485-monitor.sqlite3 \
"SELECT id, timestamp, input_dc_voltage_v, input_dc_power_w, output_ac_power_w, total_generation_kwh, fault_code FROM inverter_log ORDER BY id DESC LIMIT 10;"
```

## 설정 파일

런타임 설정은 `python-dotenv`로 파싱하는 `solar-rs485-monitor.conf` 형식을 사용합니다.

설정 파일 탐색 순서:

1. `/etc/solar-rs485-monitor.conf`
2. 명령을 실행하는 현재 작업 디렉터리의 `solar-rs485-monitor.conf`

PyPI로 시스템 전역 설치한 경우 `/etc` 아래에 설정 파일을 만듭니다.

```bash
solar-rs485-monitor --print-config-template | sudo tee /etc/solar-rs485-monitor.conf >/dev/null
sudo chmod 600 /etc/solar-rs485-monitor.conf
```

로컬 개발이나 소스 체크아웃에서는 명령을 실행하는 디렉터리에 설정 파일을 둡니다.

```bash
cp solar-rs485-monitor.conf.template solar-rs485-monitor.conf
```

로컬 `solar-rs485-monitor.conf`에는 실제 credential이 들어가므로 커밋하면 안 됩니다.

공통 설정:

```env
DASHBOARD_TITLE="Solar RS485 Monitor"
DASHBOARD_SERVER_ADDRESS="0.0.0.0"
DASHBOARD_SERVER_PORT="8501"
DASHBOARD_SERVER_HEADLESS="true"
DASHBOARD_GATHER_USAGE_STATS="false"
DASHBOARD_RUN_ON_SAVE="false"
COLLECT_INTERVAL="60"
COLLECTOR_SINKS="all"
```

`DASHBOARD_TITLE`은 Streamlit 대시보드의 브라우저 제목과 화면 상단 제목으로 사용됩니다.

`DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, `DASHBOARD_RUN_ON_SAVE`는 Streamlit 대시보드 서버의 기본 실행 옵션입니다. 명령행에 Streamlit 옵션을 명시하면 해당 값이 우선합니다.

`COLLECT_INTERVAL`은 `--loop`가 주어졌을 때만 사용하는 기본 반복 수집 간격입니다. 명령행의 `--interval` 값은 loop mode를 의미하며 항상 `COLLECT_INTERVAL`보다 우선합니다.

`COLLECTOR_SINKS`는 명령행에 sink 옵션을 하나도 주지 않았을 때만 사용됩니다. `all` 또는 `mariadb,thingspeak,opensearch` 같은 comma-separated 목록을 사용합니다.

## 설정

패키지가 PyPI에 게시된 뒤에는 다음처럼 설치합니다.

```bash
pip install solar-rs485-monitor
```

로컬 개발에서 `uv`와 프로젝트 `.venv`를 사용하는 경우:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -e .
```

설치된 콘솔 명령으로 실행합니다.

```bash
solar-rs485-monitor
```

의존성이 설치되어 있다면 소스 체크아웃에서 직접 실행할 수도 있습니다.

```bash
python src/solar_rs485_monitor/collector.py
```

## 시리얼 설정

`solar-rs485-monitor.conf`를 수정해서 `SERIAL_PORT` 한 줄만 활성화합니다.

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

자동 시작이 필요하면 원격 RS485 호스트에 설치할 수 있는 systemd unit 샘플을 [packaging/systemd/rs485-tcp-bridge.service](packaging/systemd/rs485-tcp-bridge.service)에 제공합니다.

```bash
cp packaging/systemd/rs485-tcp-bridge.service /etc/systemd/system/rs485-tcp-bridge.service
systemctl daemon-reload
systemctl enable --now rs485-tcp-bridge
systemctl status rs485-tcp-bridge
```

클라이언트 연결이 끊어진 뒤에도 fork된 `socat` 자식 프로세스가 많이 남는다면 서비스를 중지하고 stale process를 정리한 뒤, 해당 호스트의 `ExecStart` 명령에 `-T 5` 또는 `max-children=1` 추가를 검토합니다.

그 다음 WSL 개발 환경의 `solar-rs485-monitor.conf`에 다음처럼 설정합니다.

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

인버터 요청과 예상 응답 형식도 `solar-rs485-monitor.conf`에서 설정합니다.

```env
INVERTER_NAME="YOUR_INVERTER_NAME"
INVERTER_ID="1"
INVERTER_REQUEST_HEX="YOUR_INVERTER_REQUEST_HEX"
INVERTER_FRAME_LENGTH="33"
INVERTER_DATA_LENGTH="26"
INVERTER_CRC_ORDER="LH"
```

동작 테스트한 InoElectric IEPVS-3.5-G1/G2 구성의 요청 프레임은 다음과 같습니다.

```env
INVERTER_REQUEST_HEX="7e0101d188"
```

사용 중인 인버터 매뉴얼에 다른 요청 프레임이 명시되어 있다면 그 값을 사용해야 합니다.

`INVERTER_VERIFY_CRC`는 선택 항목이며 기본값은 `true`입니다.

```env
INVERTER_VERIFY_CRC="true"
```

## 실행

설치된 버전을 확인합니다.

```bash
solar-rs485-monitor --version
```

한 번 수집하고 JSON을 출력합니다.

```bash
solar-rs485-monitor
```

명령행에서 포트를 임시로 덮어씁니다.

```bash
solar-rs485-monitor --port socket://192.168.35.6:9600
```

`COLLECT_INTERVAL` 간격으로 반복 수집합니다.

```bash
solar-rs485-monitor --loop
```

명령행에서 반복 수집 간격을 임시로 덮어씁니다.

```bash
solar-rs485-monitor --interval 60
```

수집한 행을 Google Sheets에 기록합니다.

```bash
solar-rs485-monitor --google-sheet
```

수집한 데이터를 ThingSpeak에 기록합니다.

```bash
solar-rs485-monitor --thingspeak
```

수집한 데이터를 MariaDB에 기록합니다.

```bash
solar-rs485-monitor --mariadb
```

수집한 데이터를 SQLite에 기록합니다.

```bash
solar-rs485-monitor --sqlite
```

수집한 데이터를 OpenSearch 또는 Elasticsearch에 기록합니다.

```bash
solar-rs485-monitor --opensearch
```

반복 수집하면서 Google Sheets에 기록합니다.

```bash
solar-rs485-monitor --interval 60 --google-sheet
```

반복 수집하면서 ThingSpeak에 기록합니다.

```bash
solar-rs485-monitor --interval 60 --thingspeak
```

반복 수집하면서 MariaDB에 기록합니다.

```bash
solar-rs485-monitor --interval 60 --mariadb
```

반복 수집하면서 SQLite에 기록합니다.

```bash
solar-rs485-monitor --interval 60 --sqlite
```

반복 수집하면서 OpenSearch 또는 Elasticsearch에 기록합니다.

```bash
solar-rs485-monitor --interval 60 --opensearch
```

여러 sink를 함께 활성화할 수 있습니다.

```bash
solar-rs485-monitor --interval 60 --sqlite --google-sheet --thingspeak --mariadb --opensearch
```

설정된 모든 sink를 한 옵션으로 활성화할 수도 있습니다.

```bash
solar-rs485-monitor --loop --all-sinks
```

`--all-sinks`에서는 SQLite, Google Sheets, ThingSpeak, MariaDB가 활성화됩니다. OpenSearch는 `OPENSEARCH_URL`이 설정된 경우에만 활성화됩니다. OpenSearch 설정 누락을 오류로 확인하고 싶다면 `--opensearch`를 명시적으로 사용합니다.

외부 로깅 실패는 서로 분리되어 처리됩니다. SQLite, Google Sheets, ThingSpeak, MariaDB, OpenSearch가 credential 누락, 인증 실패, 네트워크 오류, rate limit, 파일시스템 권한 문제, 데이터베이스 연결 문제 등으로 실패하면 해당 sink의 오류 JSON만 출력하고 나머지 작업은 계속 진행합니다. 한 sink의 실패가 인버터 수집을 중단하거나 다른 활성 sink 실행을 막지 않습니다.

## systemd 서비스

systemd unit 샘플은 [packaging/systemd/solar-rs485-monitor.service](packaging/systemd/solar-rs485-monitor.service)에 있습니다. `solar-rs485-monitor.conf`의 `COLLECT_INTERVAL`과 `COLLECTOR_SINKS`를 사용합니다.

```ini
ExecStart=/path/to/solar-rs485-monitor --loop
```

설치 전에 대상 호스트에 맞게 아래 설정을 수정합니다.

- `ExecStart`: 설치된 `solar-rs485-monitor` 명령의 절대 경로를 사용합니다. `command -v solar-rs485-monitor`로 확인합니다.

중요: `/path/to/solar-rs485-monitor`는 placeholder입니다. 그대로 두면 systemd가 실행 파일을 찾지 못해 `status=203/EXEC`로 실패합니다.

패키지를 virtualenv 안에 설치했다면 systemd는 현재 쉘의 activate 상태를 물려받지 않습니다. 이 경우 virtualenv 안의 명령 경로를 직접 지정합니다.

```ini
ExecStart=/root/Solar-RS485-Monitor/.venv/bin/solar-rs485-monitor --loop --all-sinks
```

서비스는 일반 설정 파일 탐색 순서를 사용합니다. 특별한 이유가 없다면 데몬용 설정은 `/etc/solar-rs485-monitor.conf`에 둡니다. 데몬 수집 간격이나 sink 선택은 systemd unit을 수정하지 말고 이 설정 파일의 `COLLECT_INTERVAL`, `COLLECTOR_SINKS` 값을 변경합니다.

설치 예시:

```bash
sudo cp packaging/systemd/solar-rs485-monitor.service /etc/systemd/system/
sudo sed -i "s|/path/to/solar-rs485-monitor|$(command -v solar-rs485-monitor)|" /etc/systemd/system/solar-rs485-monitor.service
solar-rs485-monitor --print-config-template | sudo tee /etc/solar-rs485-monitor.conf >/dev/null
sudo chmod 600 /etc/solar-rs485-monitor.conf
sudo systemctl daemon-reload
sudo systemctl enable --now solar-rs485-monitor
```

서비스 제어 명령:

```bash
sudo systemctl status solar-rs485-monitor
sudo systemctl stop solar-rs485-monitor
sudo systemctl start solar-rs485-monitor
sudo journalctl -u solar-rs485-monitor -f
```

서비스에서 일부 sink만 사용하려면 `--all-sinks` 대신 `--sqlite` 또는 `--sqlite --thingspeak --mariadb --opensearch` 같은 명시적 옵션으로 바꿉니다.

## 대시보드

Streamlit 대시보드는 수집기와 같은 `solar-rs485-monitor.conf` 탐색 순서를 사용한 뒤, MariaDB 또는 SQLite를 조회해서 메트릭 차트를 표시합니다. MariaDB가 기본 선택값입니다.

로컬 실행:

```bash
solar-rs485-monitor-dashboard
```

대시보드 명령의 버전을 확인합니다.

```bash
solar-rs485-monitor-dashboard --version
```

브라우저에서 출력된 Streamlit URL을 엽니다. 사이드바에서 데이터 소스와 최대 6개월까지의 조회 기간을 선택할 수 있습니다.

대시보드는 상단에 인버터 이름과 ID를 표시하고, 수집되는 각 메트릭을 개별 차트로 렌더링합니다. 데이터베이스 전송량과 브라우저 렌더링 부담을 줄이기 위해 조회 결과는 차트 표시 전에 선택 가능한 1분, 5분, 10분, 30분 단위로 집계됩니다.

대시보드 서버 옵션은 `solar-rs485-monitor.conf`의 `DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, `DASHBOARD_RUN_ON_SAVE`에서 읽습니다. 명령행에서 override하려면:

```bash
solar-rs485-monitor-dashboard --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

선택적으로 사용할 수 있는 systemd unit 샘플은 [packaging/systemd/solar-rs485-monitor-dashboard.service](packaging/systemd/solar-rs485-monitor-dashboard.service)에 있습니다.

중요: `/path/to/solar-rs485-monitor-dashboard`는 placeholder입니다. 서비스를 시작하기 전에 반드시 각 시스템의 실제 절대 경로로 바꿔야 합니다. 그대로 두면 systemd가 실행 파일을 찾지 못해 `status=203/EXEC`로 실패합니다.

```bash
sudo cp packaging/systemd/solar-rs485-monitor-dashboard.service /etc/systemd/system/
sudo sed -i "s|/path/to/solar-rs485-monitor-dashboard|$(command -v solar-rs485-monitor-dashboard)|" /etc/systemd/system/solar-rs485-monitor-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now solar-rs485-monitor-dashboard
```

대시보드 서비스 제어 명령:

```bash
sudo systemctl status solar-rs485-monitor-dashboard
sudo journalctl -u solar-rs485-monitor-dashboard -f
```

## 패키지 빌드

이 프로젝트는 PyPI 패키지 구조로 구성되어 있습니다.

source distribution과 wheel을 생성합니다.

```bash
uv build
```

빌드 결과는 `dist/` 아래에 생성됩니다.

```text
dist/solar_rs485_monitor-VERSION.tar.gz
dist/solar_rs485_monitor-VERSION-py3-none-any.whl
```

PyPI 등록은 `.github/workflows/pypi-publish.yml`의 GitHub Actions workflow로 처리하거나, 패키지를 빌드하고 검증한 뒤 `uv publish`로 수동 등록할 수 있습니다.

## ThingSpeak 설정

`--thingspeak`를 사용하려면 `solar-rs485-monitor.conf`에 ThingSpeak Write API Key를 설정합니다.

```env
THINGSPEAK_API_KEY="YOUR_THINGSPEAK_WRITE_API_KEY"
THINGSPEAK_TIMEOUT="5.0"
```

ThingSpeak field 매핑은 채널 구성에 맞춰 고정되어 있습니다.

| ThingSpeak field | 메트릭 |
| --- | --- |
| `field1` | `input_dc_voltage_v` |
| `field2` | `input_dc_current_a` |
| `field3` | `input_dc_power_w` |
| `field4` | `output_ac_voltage_v` |
| `field5` | `output_ac_current_a` |
| `field6` | `output_ac_power_w` |
| `field7` | `total_generation_kwh` |
| `field8` | `fault_code` |

ThingSpeak는 업데이트가 거부되면 `0`을 반환합니다. 흔한 원인은 잘못된 Write API Key 또는 너무 짧은 업데이트 간격입니다. 반복 업데이트에는 최소 15초 이상의 간격을 사용합니다.

## MariaDB 설정

`--mariadb`를 사용하려면 `solar-rs485-monitor.conf`에 다음 값을 설정합니다.

```env
MARIADB_HOST="132.145.80.109"
MARIADB_PORT="3306"
MARIADB_USER="solar_logger"
MARIADB_PASSWORD="YOUR_MARIADB_PASSWORD"
MARIADB_DATABASE="solar_rs485_monitor"
MARIADB_TABLE="inverter_log"
MARIADB_CONNECT_TIMEOUT="5.0"
```

MariaDB sink는 현재 수집 메트릭과 일치하는 컬럼을 가진 `inverter_log` 테이블이 이미 존재한다고 가정합니다. 테이블 스키마에 정의된 파싱 메트릭만 insert하며, `raw_frame_hex`는 디버깅용 JSON 출력에는 포함되지만 MariaDB에는 저장하지 않습니다. 저장하려면 테이블과 sink를 함께 확장해야 합니다.

일반 로깅에는 데이터베이스 사용자에게 `INSERT` 권한만 있으면 됩니다. `SELECT` 권한은 검증이나 대시보드 구성에 유용합니다.

MariaDB 스키마와 로깅 사용자 생성 예시:

```sql
CREATE DATABASE IF NOT EXISTS solar_rs485_monitor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

USE solar_rs485_monitor;

CREATE TABLE IF NOT EXISTS inverter_log (
    id                   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    timestamp            DATETIME(6) NOT NULL COMMENT 'UTC measurement time',
    inverter_name        VARCHAR(100) NOT NULL,
    inverter_id          TINYINT UNSIGNED NOT NULL,
    input_dc_voltage_v   SMALLINT UNSIGNED COMMENT 'DC input voltage (V)',
    input_dc_current_a   FLOAT(5,2) COMMENT 'DC input current (A)',
    input_dc_power_w     INT UNSIGNED COMMENT 'DC input power (W)',
    output_ac_voltage_v  SMALLINT UNSIGNED COMMENT 'AC output voltage (V)',
    output_ac_current_a  FLOAT(5,2) COMMENT 'AC output current (A)',
    output_ac_power_w    INT UNSIGNED COMMENT 'AC output power (W)',
    output_ac_power_factor_pct FLOAT(5,2) COMMENT 'AC output power factor (%)',
    output_ac_frequency_hz     FLOAT(5,2) COMMENT 'AC output frequency (Hz)',
    total_generation_kwh FLOAT(10,3) COMMENT 'Total generation (kWh)',
    fault_code           SMALLINT UNSIGNED DEFAULT 0 COMMENT 'Fault code',
    fault                TINYINT(1) DEFAULT 0 COMMENT 'Fault status (0/1)',
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'DB insert time',
    INDEX idx_timestamp (timestamp),
    INDEX idx_inverter_id (inverter_id),
    INDEX idx_fault (fault)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='solar-rs485-monitor inverter log';

CREATE USER 'solar_logger'@'%' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT INSERT, SELECT ON solar_rs485_monitor.inverter_log TO 'solar_logger'@'%';

FLUSH PRIVILEGES;
```

`'%'` host는 모든 IP에서 원격 접속을 허용합니다. 운영 환경에서는 가능하면 수집기 호스트 IP로 제한하는 편이 좋습니다.

## SQLite 설정

SQLite는 가장 간단한 로컬 로깅 sink입니다. Python 표준 라이브러리만 사용하며, 데이터베이스 서버, 사용자 계정, 비밀번호, 네트워크 접근이 필요 없습니다.

```env
SQLITE_PATH="solar-rs485-monitor.sqlite3"
SQLITE_TABLE="inverter_log"
```

실행 예:

```bash
solar-rs485-monitor --sqlite
```

데이터베이스 파일과 테이블은 자동 생성됩니다. `SQLITE_PATH`가 상대 경로이면 명령을 실행한 현재 작업 디렉터리 기준으로 해석됩니다. systemd에서는 아래처럼 절대 경로를 사용하는 편이 좋습니다.

```env
SQLITE_PATH="/var/lib/solar-rs485-monitor/solar-rs485-monitor.sqlite3"
```

자동 생성되는 SQLite 테이블은 다음과 같습니다.

```sql
CREATE TABLE IF NOT EXISTS inverter_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    inverter_name TEXT NOT NULL,
    inverter_id INTEGER NOT NULL,
    input_dc_voltage_v INTEGER,
    input_dc_current_a REAL,
    input_dc_power_w INTEGER,
    output_ac_voltage_v INTEGER,
    output_ac_current_a REAL,
    output_ac_power_w INTEGER,
    output_ac_power_factor_pct REAL,
    output_ac_frequency_hz REAL,
    total_generation_kwh REAL,
    fault_code INTEGER DEFAULT 0,
    fault INTEGER DEFAULT 0,
    raw_frame_hex TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## OpenSearch 설정

`--opensearch`를 사용하려면 `solar-rs485-monitor.conf`에 다음 값을 설정합니다.

```env
OPENSEARCH_URL="https://YOUR_OPENSEARCH_HOST:9200"
OPENSEARCH_INDEX="solar-rs485-monitor"
OPENSEARCH_USERNAME=""
OPENSEARCH_PASSWORD=""
OPENSEARCH_TIMEOUT="5.0"
OPENSEARCH_VERIFY_TLS="true"
```

OpenSearch sink는 수집한 인버터 문서를 아래 API로 기록합니다.

```text
POST /solar-rs485-monitor/_doc
```

클러스터가 basic authentication을 요구하면 `OPENSEARCH_USERNAME`과 `OPENSEARCH_PASSWORD`를 함께 설정합니다. 자체 서명 TLS 인증서를 쓰는 환경에서는 호스트에 CA 인증서를 설치하거나 해당 환경에서 `OPENSEARCH_VERIFY_TLS="false"`를 설정합니다.

## Google Sheets 설정

`--google-sheet`를 사용하려면 `solar-rs485-monitor.conf`에 다음 값을 설정합니다.

```env
GOOGLE_SHEET_NAME="YOUR_GOOGLE_SHEET_FILE_NAME"
GOOGLE_WORKSHEET_NAME="YOUR_GOOGLE_SHEET_NAME"
```

또한 `solar-rs485-monitor.conf.template`에 있는 Google 서비스 계정 필드도 입력해야 합니다.

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
| `@timestamp` | N/A | N/A | UTC ISO 8601 | UTC 기준 수집 시각 |
| `inverter_name` | N/A | N/A | text | `INVERTER_NAME` 값 |
| `inverter_id` | frame byte 1 | 1 | numeric ID | 장치가 반환한 인버터 ID |
| `input_dc_voltage_v` | data 0-1 | 1 | V | PV 입력 DC 전압 |
| `input_dc_current_a` | data 2-3 | 1 | A | PV 입력 DC 전류 |
| `input_dc_power_w` | data 4-5 | 1 | W | PV 입력 DC 전력 |
| `output_ac_voltage_v` | data 6-7 | 1 | V | 계통 연계 AC 출력 전압 |
| `output_ac_current_a` | data 8-9 | 1 | A | 계통 연계 AC 출력 전류 |
| `output_ac_power_w` | data 10-11 | 1 | W | 계통 연계 AC 출력 전력 |
| `output_ac_power_factor_pct` | data 12-13 | 0.1 | % | 계통 연계 AC 출력 역률 |
| `output_ac_frequency_hz` | data 14-15 | 0.1 | Hz | 계통 연계 AC 출력 주파수 |
| `total_generation_kwh` | data 16-23 | 0.001 | kWh | 누적 발전량 |
| `fault_code` | data 24-25 | 1 | code | 원시 fault 코드 |
| `fault` | `fault_code`에서 파생 | N/A | 0/1 | `fault_code != 0`이면 `1`, 아니면 `0` |
| `raw_frame_hex` | full frame | N/A | hex bytes | 디버깅용 원시 응답 프레임 |

성공한 읽기 결과 예시:

```json
{
  "@timestamp": "2026-06-29T00:00:00+00:00",
  "inverter_name": "YOUR_INVERTER_NAME",
  "inverter_id": 1,
  "input_dc_voltage_v": 0,
  "input_dc_current_a": 0,
  "input_dc_power_w": 0,
  "output_ac_voltage_v": 0,
  "output_ac_current_a": 0,
  "output_ac_power_w": 0,
  "output_ac_power_factor_pct": 0.0,
  "output_ac_frequency_hz": 0.0,
  "total_generation_kwh": 0.0,
  "fault_code": 0,
  "fault": 0,
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
- `ThingSpeak update rejected`: `THINGSPEAK_API_KEY`를 확인하고 업데이트 간격을 최소 15초 이상으로 설정합니다.
- `MARIADB_PASSWORD is not set`: `--mariadb` 실행 전에 `solar-rs485-monitor.conf`에 MariaDB 비밀번호를 설정합니다.
- `MariaDB logging failed`: `MARIADB_HOST`, `MARIADB_PORT`, 방화벽 정책, DB 권한, 사용자 이름, 비밀번호, 데이터베이스 이름, 테이블 이름을 확인합니다.
- `SQLite unable to open database file`: `SQLITE_PATH`와 디렉터리 쓰기 권한을 확인합니다.
- `OPENSEARCH_URL is not set`: `--opensearch` 실행 전에 OpenSearch endpoint를 설정합니다.
- `OpenSearch request failed`: endpoint, index 권한, 사용자 이름, 비밀번호, TLS 설정, 클러스터 네트워크 접근을 확인합니다.
- `Google Sheet not found or access denied`: 스프레드시트를 `GOOGLE_CLIENT_EMAIL`에 공유합니다.
- `Google worksheet not found`: 워크시트 탭을 만들거나 `GOOGLE_WORKSHEET_NAME`을 수정합니다.
