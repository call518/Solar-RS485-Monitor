# Solar-RS485-Monitor

Solar inverter monitoring script for RS485/serial communication.

The collector reads inverter data, prints the parsed result as JSON, and can optionally write the result to external logging sinks.

Optional logging sinks are implemented as separate modules under `src/solar_rs485_monitor/sinks/`. This keeps inverter collection separate from external logging integrations such as SQLite, Google Sheets, ThingSpeak, MariaDB, and OpenSearch or Elasticsearch.

## Collected Data at a Glance

When the current parser is used with a supported InoElectric IEPVS-3.5-G1/G2 inverter, each successful read produces these core values:

| Category | Metric | Meaning |
| --- | --- | --- |
| Metadata | `@timestamp` | UTC collection time |
| Metadata | `inverter_name` | Configured inverter name |
| Metadata | `inverter_id` | Inverter ID returned by the device |
| DC input | `input_dc_voltage_v` | PV-side DC input voltage |
| DC input | `input_dc_current_a` | PV-side DC input current |
| DC input | `input_dc_power_w` | PV-side DC input power |
| AC output | `output_ac_voltage_v` | Grid-side AC output voltage |
| AC output | `output_ac_current_a` | Grid-side AC output current |
| AC output | `output_ac_power_w` | Grid-side AC output power |
| AC output | `output_ac_power_factor_pct` | Grid-side AC output power factor |
| AC output | `output_ac_frequency_hz` | Grid-side AC output frequency |
| Generation | `total_generation_kwh` | Total accumulated generation |
| Status | `fault_code` | Raw inverter fault code |
| Status | `fault` | Numeric fault status derived from `fault_code` |
| Debug | `raw_frame_hex` | Raw response frame for troubleshooting |

The same parsed record can be printed as JSON and optionally written to SQLite, Google Sheets, ThingSpeak, MariaDB, and OpenSearch or Elasticsearch.

## Supported Inverter Scope

The current code was written and tested for InoElectric IEPVS-3.5-G1/G2 inverters.

The request frame, response frame length, data offsets, scaling rules, CRC order, and metric interpretation are product-specific. If you use a different inverter model, check that product's specification or manual first, then update both sides of the protocol handling:

- Request frame: set `INVERTER_REQUEST_HEX` to the product-specific request frame. If your environment describes this as a TCP header or protocol header, treat that product-specific header/request bytes as part of this value.
- Response validation: set `INVERTER_FRAME_LENGTH`, `INVERTER_DATA_LENGTH`, `INVERTER_CRC_ORDER`, and `INVERTER_ID` according to the product's response format.
- Response parsing: update `parse_frame()` in [src/solar_rs485_monitor/collector.py](src/solar_rs485_monitor/collector.py) if the product returns fields at different byte offsets, uses different units, or uses different scaling.

Do not assume another RS485 inverter will expose the same data layout just because the serial/TCP connection succeeds.

## Current Connection Modes

The serial connection is configured with `SERIAL_PORT` in `solar-rs485-monitor.conf`.

Two modes are supported:

1. Local USB RS485 adapter
2. TCP access to the RS485 USB adapter attached to the remote RS485 host using `socat`

Internally, the code uses `pyserial`'s `serial_for_url()`, so both a normal device path and a pyserial URL work with the same setting.

## Quickstart With SQLite

This is the shortest path to collect data and inspect stored rows without any external logging service.

1. Create a virtual environment:

```bash
uv venv .venv
```

2. Install the package in that environment:

```bash
./.venv/bin/pip install solar-rs485-monitor
```

3. Create the config file at `/etc/solar-rs485-monitor.conf`:

```bash
./.venv/bin/solar-rs485-monitor --print-config-template | sudo tee /etc/solar-rs485-monitor.conf >/dev/null
```

4. Edit `/etc/solar-rs485-monitor.conf` and set at least these values:

```env
SERIAL_PORT="/dev/ttyUSB0"
INVERTER_NAME="YOUR_INVERTER_NAME"
INVERTER_ID="1"
INVERTER_REQUEST_HEX="YOUR_INVERTER_REQUEST_HEX"
SQLITE_PATH="/tmp/solar-rs485-monitor.sqlite3"
PYTHON_VENV_PATH="/absolute/path/to/.venv"
```

5. Start collection and write to SQLite:

```bash
./.venv/bin/solar-rs485-monitor --sqlite
```

6. Query the latest rows:

```bash
sqlite3 -header -column /tmp/solar-rs485-monitor.sqlite3 \
"SELECT id, timestamp, input_dc_voltage_v, input_dc_power_w, output_ac_power_w, total_generation_kwh, fault_code FROM inverter_log ORDER BY id DESC LIMIT 10;"
```

## Configuration File

Runtime configuration uses `solar-rs485-monitor.conf` format, parsed with `python-dotenv`.

Configuration lookup order:

1. `/etc/solar-rs485-monitor.conf`
2. `solar-rs485-monitor.conf` in the current working directory where the command is run

For a system-wide PyPI installation, create the config under `/etc`:

```bash
solar-rs485-monitor --print-config-template | sudo tee /etc/solar-rs485-monitor.conf >/dev/null
sudo chmod 600 /etc/solar-rs485-monitor.conf
```

For local development or a source checkout, keep the config in the directory where you run the command:

```bash
cp solar-rs485-monitor.conf.template solar-rs485-monitor.conf
```

The local `solar-rs485-monitor.conf` contains real credentials and must not be committed.

General settings:

```env
DASHBOARD_TITLE="Solar RS485 Monitor"
DASHBOARD_LANGUAGE="Korean"
DASHBOARD_SERVER_ADDRESS="0.0.0.0"
DASHBOARD_SERVER_PORT="8501"
DASHBOARD_SERVER_HEADLESS="true"
DASHBOARD_GATHER_USAGE_STATS="false"
DASHBOARD_RUN_ON_SAVE="false"
DASHBOARD_AUTH_ENABLED="false"
DASHBOARD_AUTH_USERS=""
DASHBOARD_AUTH_COOKIE_SECRET="CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS="86400"
DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS="admin"
COLLECT_INTERVAL="60"
PYTHON_VENV_PATH="/opt/myapp/.venv"
COLLECTOR_SINKS="all"
```

`DASHBOARD_TITLE` sets the Streamlit dashboard browser title and page heading.

`DASHBOARD_LANGUAGE` sets the default dashboard UI language at startup. It is case-insensitive and accepts `English` or `Korean`. Users can still change language from the sidebar after loading.

`DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, and `DASHBOARD_RUN_ON_SAVE` set the default Streamlit dashboard server options. Explicit command-line Streamlit options still override these values.

`DASHBOARD_AUTH_ENABLED` enables the built-in dashboard login. `DASHBOARD_AUTH_USERS` stores comma-separated `username:password_hash` entries generated by `solar-rs485-monitor-dashboard --hash-password`. `DASHBOARD_AUTH_COOKIE_SECRET` signs the browser login cookie, and `DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS` controls how long normal logins survive refreshes and reconnects. `DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS` defines comma-separated usernames that receive long-lived cookies. If not set, `admin` remains persistent for backward compatibility.

`COLLECT_INTERVAL` is used only when `--loop` is provided. A command-line `--interval` value implies loop mode and always overrides `COLLECT_INTERVAL`. Values below 10 seconds are clamped to 10 seconds to reduce accidental over-collection.

`PYTHON_VENV_PATH` is used by the sample systemd units to prepend `${PYTHON_VENV_PATH}/bin` to `PATH` before launching the collector and dashboard commands.

`COLLECTOR_SINKS` is used only when no sink CLI flags are provided. Use `all` or a comma-separated list such as `mariadb,thingspeak,opensearch`.

## Setup

Install from PyPI after the package is published:

```bash
pip install solar-rs485-monitor
```

For local development with `uv` and the project `.venv`:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -e .
```

Run the installed console command:

```bash
solar-rs485-monitor
```

You can also run directly from a source checkout after installing dependencies:

```bash
python src/solar_rs485_monitor/collector.py
```

## Serial Configuration

Edit `solar-rs485-monitor.conf` and enable exactly one `SERIAL_PORT` line.

For direct USB access:

```env
SERIAL_PORT="/dev/ttyUSB0"
#SERIAL_PORT="socket://192.168.35.6:9600"
```

For the current development setup, where the RS485 USB adapter is attached to a remote RS485 host and WSL connects to it over TCP:

```env
#SERIAL_PORT="/dev/ttyUSB0"
SERIAL_PORT="socket://192.168.35.6:9600"
```

Keep both lines in the file if that is convenient, but only one should be uncommented. If both are uncommented, the last parsed value can win and make the active connection unclear.

Other serial settings:

```env
SERIAL_BAUDRATE="9600"
SERIAL_TIMEOUT="1.0"
```

## Remote RS485 Host TCP Forwarding

In this project setup, the remote RS485 host is the device physically connected to the inverter RS485 USB converter. Because VS Code and development work may run from WSL, that host forwards `/dev/ttyUSB0` over TCP with `socat`.

```bash
/usr/bin/socat TCP-LISTEN:9600,reuseaddr,fork FILE:/dev/ttyUSB0,raw,echo=0
```

An optional systemd unit sample is available at [packaging/systemd/rs485-tcp-bridge.service](packaging/systemd/rs485-tcp-bridge.service). Install it on the remote RS485 host when you want the TCP bridge to start automatically:

```bash
cp packaging/systemd/rs485-tcp-bridge.service /etc/systemd/system/rs485-tcp-bridge.service
systemctl daemon-reload
systemctl enable --now rs485-tcp-bridge
systemctl status rs485-tcp-bridge
```

If many forked `socat` child processes remain after clients disconnect, stop the service, clear the stale processes, and consider adding `-T 5` or `max-children=1` to the `ExecStart` command for that host.

Then set `solar-rs485-monitor.conf` in the WSL development environment:

```env
SERIAL_PORT="socket://RS485_HOST_IP:9600"
```

Example:

```env
SERIAL_PORT="socket://192.168.35.6:9600"
```

If the inverter does not respond over TCP, also check that the remote RS485 host serial device is using the expected speed. Depending on the adapter and OS configuration, you may need to include the baud rate in the `socat` file options, for example:

```bash
/usr/bin/socat TCP-LISTEN:9600,reuseaddr,fork FILE:/dev/ttyUSB0,raw,echo=0,b9600
```

## Inverter Protocol Configuration

The inverter request and expected response format are also configured in `solar-rs485-monitor.conf`.

```env
INVERTER_NAME="YOUR_INVERTER_NAME"
INVERTER_ID="1"
INVERTER_REQUEST_HEX="YOUR_INVERTER_REQUEST_HEX"
INVERTER_FRAME_LENGTH="33"
INVERTER_DATA_LENGTH="26"
INVERTER_CRC_ORDER="LH"
```

For the tested InoElectric IEPVS-3.5-G1/G2 setup, the request frame is:

```env
INVERTER_REQUEST_HEX="7e0101d188"
```

Use a different value if your inverter manual specifies a different request frame.

`INVERTER_VERIFY_CRC` is optional and defaults to `true`.

```env
INVERTER_VERIFY_CRC="true"
```

## Run

Show the installed version:

```bash
solar-rs485-monitor --version
```

Collect once and print JSON:

```bash
solar-rs485-monitor
```

Override the port temporarily from the command line:

```bash
solar-rs485-monitor --port socket://192.168.35.6:9600
```

Repeat collection using `COLLECT_INTERVAL`:

```bash
solar-rs485-monitor --loop
```

Override the repeat interval temporarily from the command line:

```bash
solar-rs485-monitor --interval 60
```

Write collected rows to Google Sheets:

```bash
solar-rs485-monitor --google-sheet
```

Write collected data to ThingSpeak:

```bash
solar-rs485-monitor --thingspeak
```

Write collected data to MariaDB:

```bash
solar-rs485-monitor --mariadb
```

Write collected data to SQLite:

```bash
solar-rs485-monitor --sqlite
```

Write collected data to OpenSearch or Elasticsearch:

```bash
solar-rs485-monitor --opensearch
```

Repeat collection and write to Google Sheets:

```bash
solar-rs485-monitor --interval 60 --google-sheet
```

Repeat collection and write to ThingSpeak:

```bash
solar-rs485-monitor --interval 60 --thingspeak
```

Repeat collection and write to MariaDB:

```bash
solar-rs485-monitor --interval 60 --mariadb
```

Repeat collection and write to SQLite:

```bash
solar-rs485-monitor --interval 60 --sqlite
```

Repeat collection and write to OpenSearch or Elasticsearch:

```bash
solar-rs485-monitor --interval 60 --opensearch
```

Multiple sinks can be enabled together:

```bash
solar-rs485-monitor --interval 60 --sqlite --google-sheet --thingspeak --mariadb --opensearch
```

Or enable every configured sink with one option:

```bash
solar-rs485-monitor --loop --all-sinks
```

With `--all-sinks`, SQLite, Google Sheets, ThingSpeak, and MariaDB are enabled. OpenSearch is enabled only when `OPENSEARCH_URL` is set. Use `--opensearch` explicitly if you want missing OpenSearch configuration to be reported as an error.

External logging failures are isolated. If SQLite, Google Sheets, ThingSpeak, MariaDB, or OpenSearch fails because of a missing credential, authentication error, network error, rate limit, filesystem permission issue, or database connection issue, the collector prints an error JSON for that sink and continues the remaining work. A failed sink does not stop inverter collection or block another enabled sink.

## systemd Service

A sample systemd unit is available at [packaging/systemd/solar-rs485-monitor.service](packaging/systemd/solar-rs485-monitor.service). It reads `/etc/solar-rs485-monitor.conf` via `EnvironmentFile` and builds `PATH` using `PYTHON_VENV_PATH`:

```ini
EnvironmentFile=/etc/solar-rs485-monitor.conf
ExecStart=/usr/bin/env PATH=${PYTHON_VENV_PATH}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin solar-rs485-monitor --loop
```

Before installing it, set `PYTHON_VENV_PATH` in `/etc/solar-rs485-monitor.conf` to your virtualenv root, for example `/opt/myapp/.venv`.

The service uses the normal config lookup order. Put the daemon config at `/etc/solar-rs485-monitor.conf` unless you have a specific reason to keep it next to the executable. Change `COLLECT_INTERVAL` or `COLLECTOR_SINKS` in that config file to adjust daemon behavior without editing the systemd unit.

Example install commands:

```bash
sudo cp packaging/systemd/solar-rs485-monitor.service /etc/systemd/system/
solar-rs485-monitor --print-config-template | sudo tee /etc/solar-rs485-monitor.conf >/dev/null
sudo chmod 600 /etc/solar-rs485-monitor.conf
sudo systemctl daemon-reload
sudo systemctl enable --now solar-rs485-monitor
```

Service control commands:

```bash
sudo systemctl status solar-rs485-monitor
sudo systemctl stop solar-rs485-monitor
sudo systemctl start solar-rs485-monitor
sudo journalctl -u solar-rs485-monitor -f
```

If you only want selected sinks in the service, replace `--all-sinks` with explicit flags such as `--sqlite` or `--sqlite --thingspeak --mariadb --opensearch`.

## Dashboard

The Streamlit dashboard reads the same `solar-rs485-monitor.conf` lookup order as the collector, then queries MariaDB or SQLite and displays metric charts. MariaDB is selected by default.

Run locally:

```bash
solar-rs485-monitor-dashboard
```

Show the dashboard command version:

```bash
solar-rs485-monitor-dashboard --version
```

Open the displayed Streamlit URL in a browser. The sidebar lets you select the data source and time range up to 6 months.

The dashboard shows inverter name and ID at the top, then renders each collected metric as a separate chart. Query results are aggregated into selectable 10 second, 30 second, 1 minute, 2 minute, 5 minute, 10 minute, 15 minute, or 30 minute buckets before charting to reduce database transfer and browser rendering cost.

Dashboard server options are read from `DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, and `DASHBOARD_RUN_ON_SAVE` in `solar-rs485-monitor.conf`. The dashboard auto-refresh interval is selected in the sidebar and refreshes the dashboard content area without reloading the browser page. To override Streamlit server options from the command line:

```bash
solar-rs485-monitor-dashboard --server.address 0.0.0.0 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Optional dashboard login uses local PBKDF2-SHA256 password hashes and does not require an external authentication service. Generate a hash, then add it to `/etc/solar-rs485-monitor.conf`:

```bash
solar-rs485-monitor-dashboard --hash-password
```

```env
DASHBOARD_AUTH_ENABLED="true"
DASHBOARD_AUTH_USERS="admin:pbkdf2_sha256$260000$..."
DASHBOARD_AUTH_COOKIE_SECRET="replace-with-a-long-random-secret"
DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS="86400"
DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS="admin,susunwha"
```

For multiple users, separate entries with commas. Login state is stored in a signed browser cookie, so page refreshes do not require another login until the cookie expires. Users listed in `DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS` are treated as persistent and remain logged in until logout unless the cookie is removed or the cookie secret changes. This is application-level login; use HTTPS, a reverse proxy, firewall rules, or a private network when exposing the dashboard outside a trusted LAN.

An optional systemd unit sample is available at [packaging/systemd/solar-rs485-monitor-dashboard.service](packaging/systemd/solar-rs485-monitor-dashboard.service). It also uses `EnvironmentFile=/etc/solar-rs485-monitor.conf` and `PYTHON_VENV_PATH` to resolve the command from virtualenv `PATH`.

```bash
sudo cp packaging/systemd/solar-rs485-monitor-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now solar-rs485-monitor-dashboard
```

Dashboard service control commands:

```bash
sudo systemctl status solar-rs485-monitor-dashboard
sudo journalctl -u solar-rs485-monitor-dashboard -f
```

## Package Build

This project is structured as a PyPI package.

Build the source distribution and wheel:

```bash
uv build
```

The build outputs are created under `dist/`:

```text
dist/solar_rs485_monitor-VERSION.tar.gz
dist/solar_rs485_monitor-VERSION-py3-none-any.whl
```

PyPI publishing can be handled by the GitHub Actions workflow in `.github/workflows/pypi-publish.yml`, or manually with `uv publish` after building and verifying the package.

## ThingSpeak Configuration

To use `--thingspeak`, configure a ThingSpeak Write API Key in `solar-rs485-monitor.conf`.

```env
THINGSPEAK_API_KEY="YOUR_THINGSPEAK_WRITE_API_KEY"
THINGSPEAK_TIMEOUT="5.0"
```

The ThingSpeak field mapping is fixed to match the configured channel:

| ThingSpeak field | Metric |
| --- | --- |
| `field1` | `input_dc_voltage_v` |
| `field2` | `input_dc_current_a` |
| `field3` | `input_dc_power_w` |
| `field4` | `output_ac_voltage_v` |
| `field5` | `output_ac_current_a` |
| `field6` | `output_ac_power_w` |
| `field7` | `total_generation_kwh` |
| `field8` | `fault_code` |

ThingSpeak returns `0` when an update is rejected. Common causes are an invalid Write API Key or updates sent too frequently. Use an interval of at least 15 seconds for repeated updates.

## MariaDB Configuration

To use `--mariadb`, configure these values in `solar-rs485-monitor.conf`:

```env
MARIADB_HOST="132.145.80.109"
MARIADB_PORT="3306"
MARIADB_USER="solar_logger"
MARIADB_PASSWORD="YOUR_MARIADB_PASSWORD"
MARIADB_DATABASE="solar_rs485_monitor"
MARIADB_TABLE="inverter_log"
MARIADB_CONNECT_TIMEOUT="5.0"
```

The sink expects the `inverter_log` table to already exist with columns matching the current collected metrics. It inserts only the parsed metric fields defined by the table schema; `raw_frame_hex` is printed in JSON for debugging but is not stored in MariaDB unless the table and sink are extended.

The database user only needs `INSERT` for normal logging. `SELECT` can be useful for verification and dashboards.

Example MariaDB schema and logging user:

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

The `%` host allows remote access from any IP. For production, restrict it to the collector host IP whenever possible.

## SQLite Configuration

SQLite is the simplest local logging sink. It uses Python's standard library and does not require a database server, user account, password, or network access.

```env
SQLITE_PATH="solar-rs485-monitor.sqlite3"
SQLITE_TABLE="inverter_log"
```

Run with:

```bash
solar-rs485-monitor --sqlite
```

The database file and table are created automatically. If `SQLITE_PATH` is relative, it is resolved from the current working directory where the command is run. For systemd, prefer an absolute path such as:

```env
SQLITE_PATH="/var/lib/solar-rs485-monitor/solar-rs485-monitor.sqlite3"
```

The auto-created SQLite table is:

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

## OpenSearch Configuration

To use `--opensearch`, configure these values in `solar-rs485-monitor.conf`:

```env
OPENSEARCH_URL="https://YOUR_OPENSEARCH_HOST:9200"
OPENSEARCH_INDEX="solar-rs485-monitor"
OPENSEARCH_USERNAME=""
OPENSEARCH_PASSWORD=""
OPENSEARCH_TIMEOUT="5.0"
OPENSEARCH_VERIFY_TLS="true"
```

The sink writes each collected inverter document to:

```text
POST /solar-rs485-monitor/_doc
```

Set `OPENSEARCH_USERNAME` and `OPENSEARCH_PASSWORD` together when the cluster requires basic authentication. For self-signed TLS certificates, either install the CA certificate on the host or set `OPENSEARCH_VERIFY_TLS="false"` for that environment.

## Google Sheets Configuration

To use `--google-sheet`, configure these values in `solar-rs485-monitor.conf`:

```env
GOOGLE_SHEET_NAME="YOUR_GOOGLE_SHEET_FILE_NAME"
GOOGLE_WORKSHEET_NAME="YOUR_GOOGLE_SHEET_NAME"
```

Also provide the Google service account fields from `solar-rs485-monitor.conf.template`.

The spreadsheet must be shared with the service account email:

```env
GOOGLE_CLIENT_EMAIL="service-account@your-project-id.iam.gserviceaccount.com"
```

The collector creates the header row automatically if the worksheet is empty. If row 1 already exists and does not match the expected schema, the script stops with a header mismatch error.

## Output

The script prints one JSON object per collection attempt.

## Collected Metrics

For InoElectric IEPVS-3.5-G1/G2, the current parser interprets the response data payload as follows. Multi-byte values are decoded as big-endian unsigned integers.

| Output field | Data bytes | Scale | Unit | Description |
| --- | ---: | ---: | --- | --- |
| `@timestamp` | N/A | N/A | UTC ISO 8601 | UTC collection timestamp |
| `inverter_name` | N/A | N/A | text | Name from `INVERTER_NAME` |
| `inverter_id` | frame byte 1 | 1 | numeric ID | Inverter ID returned by the device |
| `input_dc_voltage_v` | data 0-1 | 1 | V | DC input voltage from the PV side |
| `input_dc_current_a` | data 2-3 | 1 | A | DC input current from the PV side |
| `input_dc_power_w` | data 4-5 | 1 | W | DC input power from the PV side |
| `output_ac_voltage_v` | data 6-7 | 1 | V | Grid-side AC output voltage |
| `output_ac_current_a` | data 8-9 | 1 | A | Grid-side AC output current |
| `output_ac_power_w` | data 10-11 | 1 | W | Grid-side AC output power |
| `output_ac_power_factor_pct` | data 12-13 | 0.1 | % | Grid-side AC output power factor |
| `output_ac_frequency_hz` | data 14-15 | 0.1 | Hz | Grid-side AC output frequency |
| `total_generation_kwh` | data 16-23 | 0.001 | kWh | Total accumulated generation |
| `fault_code` | data 24-25 | 1 | code | Raw fault code |
| `fault` | derived from `fault_code` | N/A | 0/1 | `1` when `fault_code != 0`, otherwise `0` |
| `raw_frame_hex` | full frame | N/A | hex bytes | Raw response frame for debugging |

Successful reads include fields such as:

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

Errors are also printed as JSON:

```json
{
  "@timestamp": "2026-06-29T00:00:00+00:00",
  "inverter_name": "YOUR_INVERTER_NAME",
  "error": "No response from inverter"
}
```

## Troubleshooting

- `No response from inverter`: check `SERIAL_PORT`, remote RS485 host IP, TCP port, RS485 wiring, inverter ID, and baud rate.
- `Connection refused`: `socat` is not running, the IP/port is wrong, or a firewall is blocking access.
- `CRC mismatch`: check `INVERTER_CRC_ORDER`, request bytes, and whether the expected frame length matches the actual inverter response.
- `ThingSpeak update rejected`: check `THINGSPEAK_API_KEY` and use an update interval of at least 15 seconds.
- `MARIADB_PASSWORD is not set`: set the MariaDB password in `solar-rs485-monitor.conf` before running with `--mariadb`.
- `MariaDB logging failed`: check `MARIADB_HOST`, `MARIADB_PORT`, firewall rules, database grants, username, password, database name, and table name.
- `SQLite unable to open database file`: check `SQLITE_PATH` and directory write permissions.
- `OPENSEARCH_URL is not set`: set the OpenSearch endpoint before running with `--opensearch`.
- `OpenSearch request failed`: check the endpoint, index permission, username, password, TLS setting, and cluster network access.
- `Google Sheet not found or access denied`: share the spreadsheet with `GOOGLE_CLIENT_EMAIL`.
- `Google worksheet not found`: create the worksheet tab or fix `GOOGLE_WORKSHEET_NAME`.
