# Solar-RS485-Monitor

Solar inverter monitoring script for RS485/serial communication.

The collector reads inverter data, prints the parsed result as JSON, and can optionally write the result to external logging sinks.

The current parser and protocol defaults are validated for InoElectric IEPVS-3.5-G1/G2.

Optional logging sinks are implemented as separate modules under `src/solar_rs485_monitor/sinks/`. Telegram event notifications are implemented under `src/solar_rs485_monitor/alerts/`. This keeps inverter collection separate from external logging integrations such as SQLite, Google Sheets, ThingSpeak, MariaDB, Supabase (PostgreSQL), and OpenSearch or Elasticsearch, while handling alert delivery separately.

## Architecture Diagram

<a href="https://deepwiki.com/call518/Solar-RS485-Monitor" target="_blank" rel="noopener noreferrer">DeepWiki</a>

![Architecture Diagram](images/DeepWiki-Architecture-Diagram.png)

## Start Here

- Check prerequisites in [Setup](#setup) and [Configuration File](#configuration-file).
- For the fastest first run, start from [Quickstart With SQLite](#quickstart-with-sqlite).
- Dashboard and sink-specific settings are documented in later sections.

## Sink Screenshots (Optional Preview)

<table>
  <tr>
    <td align="center">
      <a href="images/ScreenShot-001-Streamlit.png">
        <img src="images/ScreenShot-001-Streamlit.png" alt="Streamlit dashboard" width="320" height="180" style="object-fit: cover; object-position: center;" />
      </a>
      <br />Streamlit
    </td>
    <td align="center">
      <a href="images/ScreenShot-002-ThingSpeak.png">
        <img src="images/ScreenShot-002-ThingSpeak.png" alt="ThingSpeak" width="320" height="180" style="object-fit: cover; object-position: center;" />
      </a>
      <br />ThingSpeak
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="images/ScreenShot-003-Google-Sheets.png">
        <img src="images/ScreenShot-003-Google-Sheets.png" alt="Google Sheets" width="320" height="180" style="object-fit: cover; object-position: center;" />
      </a>
      <br />Google Sheets
    </td>
    <td align="center">
      <a href="images/ScreenShot-004-OpenSearch.png">
        <img src="images/ScreenShot-004-OpenSearch.png" alt="OpenSearch" width="320" height="180" style="object-fit: cover; object-position: center;" />
      </a>
      <br />OpenSearch
    </td>
  </tr>
</table>

## Physical Installation Photos (Optional Preview)

<table>
  <tr>
    <td align="center">
      <a href="images/Photo-01-inverter-Inoelectric-IEPVS.jpg">
        <img src="images/Photo-01-inverter-Inoelectric-IEPVS.jpg" alt="Inverter unit" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />Inverter unit
    </td>
    <td align="center">
      <a href="images/Photo-02-RS485-Cable.jpg">
        <img src="images/Photo-02-RS485-Cable.jpg" alt="RS485 cable path A" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />RS485 cable path A
    </td>
    <td align="center">
      <a href="images/Photo-03-RS485-Cable.jpg">
        <img src="images/Photo-03-RS485-Cable.jpg" alt="RS485 cable path B" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />RS485 cable path B
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="images/Photo-04-RS485-Cable.jpg">
        <img src="images/Photo-04-RS485-Cable.jpg" alt="RS485 cable terminal" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />RS485 cable terminal
    </td>
    <td align="center">
      <a href="images/Photo-05-RS485-Cable.jpg">
        <img src="images/Photo-05-RS485-Cable.jpg" alt="RS485 cable routing" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />RS485 cable routing
    </td>
    <td align="center">
      <a href="images/Photo-06-FT232-RS485toUSB-Converter.jpg">
        <img src="images/Photo-06-FT232-RS485toUSB-Converter.jpg" alt="FT232 RS485 to USB converter" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />FT232 RS485 to USB converter
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="images/Photo-07-RS485-Cable.jpg">
        <img src="images/Photo-07-RS485-Cable.jpg" alt="RS485 cable connection" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />RS485 cable connection
    </td>
    <td align="center">
      <a href="images/Photo-08-RaspberryPi.jpg">
        <img src="images/Photo-08-RaspberryPi.jpg" alt="Raspberry Pi host A" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />Raspberry Pi host A
    </td>
    <td align="center">
      <a href="images/Photo-09-RaspberryPi.jpg">
        <img src="images/Photo-09-RaspberryPi.jpg" alt="Raspberry Pi host B" width="240" height="135" style="object-fit: cover; object-position: center;" />
      </a>
      <br />Raspberry Pi host B
    </td>
  </tr>
</table>

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
| Debug | `raw_frame_hex` | Raw response frame for troubleshooting |

The same parsed record can be printed as JSON and optionally written to SQLite, Google Sheets, ThingSpeak, MariaDB, and OpenSearch or Elasticsearch. Telegram is used as an alert channel for fault events.

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

The config template marks measurement-only requirements with `[Required]`.
For the minimum operation test, leave all `[Sink][Optional]` and
`[Alert][Optional]` settings unused and set `COLLECTOR_SINKS=""` plus
`ALERT_CHANNELS=""`; the collector will only read the inverter and print JSON.
The `[Sink]` and `[Alert]` labels still identify which feature each optional
setting belongs to.

General settings:

```env
DASHBOARD_TITLE="Solar RS485 Monitor"
DASHBOARD_LANGUAGE="English"
DASHBOARD_SERVER_ADDRESS="0.0.0.0"
DASHBOARD_SERVER_PORT="8501"
DASHBOARD_SERVER_HEADLESS="true"
DASHBOARD_GATHER_USAGE_STATS="false"
DASHBOARD_RUN_ON_SAVE="false"
DASHBOARD_AUTO_REFRESH_SECONDS="60"
DASHBOARD_MAX_POINTS="10000"
DASHBOARD_DEFAULT_RANGE="Last 7 days"
DASHBOARD_TOTAL_GENERATION_DAYS="14"
DASHBOARD_DAILY_GENERATION_DAYS="14"
DASHBOARD_WEEKLY_GENERATION_WEEKS="16"
DASHBOARD_MONTHLY_GENERATION_MONTHS="12"
DASHBOARD_YEARLY_GENERATION_YEARS="10"
DASHBOARD_AUTH_ENABLED="false"
DASHBOARD_AUTH_USERS=""
DASHBOARD_AUTH_COOKIE_SECRET="CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS="86400"
DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS="admin"
COLLECT_INTERVAL="60"
PYTHON_VENV_PATH="/opt/myapp/.venv"
COLLECTOR_SINKS=""
ALERT_CHANNELS=""
```

`DASHBOARD_TITLE` sets the Streamlit dashboard browser title and page heading.

`DASHBOARD_LANGUAGE` sets the default dashboard UI language at startup. It is case-insensitive and accepts `English` or `Korean`. Users can still change language from the sidebar after loading.

The top status badge uses Bit 0 in `fault_code` (inverter operation flag) to determine `STANDBY`. Fault detection is based on Bit 1+; if any Bit 1+ is active, the badge shows `FAULT`. Otherwise, it shows `STANDBY` when Bit 0 is `1`, and `NORMAL` when Bit 0 is `0`.

`DASHBOARD_AUTO_REFRESH_SECONDS` sets the default auto-refresh option selected in the dashboard sidebar. Supported values are `0`, `60`, `120`, `300`, and `600`. A value between `1` and `59` is clamped to `60` for safety.

`DASHBOARD_MAX_POINTS` sets the maximum aggregated points queried for charts. This value is config-only (not editable from the dashboard UI). Allowed range is `100..300000`, and the default is `10000`.

`DASHBOARD_DEFAULT_RANGE` is used to calculate the initial start and end dates when the dashboard first loads. The default is `Last 7 days`, and users can still change the start and end dates from the sidebar.

`DASHBOARD_TOTAL_GENERATION_DAYS`, `DASHBOARD_DAILY_GENERATION_DAYS`, `DASHBOARD_WEEKLY_GENERATION_WEEKS`, `DASHBOARD_MONTHLY_GENERATION_MONTHS`, and `DASHBOARD_YEARLY_GENERATION_YEARS` set the minimum or fixed display windows for the total, daily, weekly, monthly, and yearly generation charts. These values are config-only and are not exposed in the dashboard UI.

`DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, and `DASHBOARD_RUN_ON_SAVE` set the default Streamlit dashboard server options. Explicit command-line Streamlit options still override these values.

`DASHBOARD_AUTH_ENABLED` enables the built-in dashboard login. `DASHBOARD_AUTH_USERS` stores comma-separated `username:password_hash` entries generated by `solar-rs485-monitor-dashboard --hash-password`. `DASHBOARD_AUTH_COOKIE_SECRET` signs the browser login cookie, and `DASHBOARD_AUTH_COOKIE_MAX_AGE_SECONDS` controls how long normal logins survive refreshes and reconnects. `DASHBOARD_AUTH_COOKIE_PERSISTENT_USERS` defines comma-separated usernames that receive long-lived cookies. If not set, `admin` remains persistent for backward compatibility.

`COLLECT_INTERVAL` is used only when `--loop` is provided. A command-line `--interval` value implies loop mode and always overrides `COLLECT_INTERVAL`. Values below 60 seconds are clamped to 60 seconds to reduce accidental over-collection.

`PYTHON_VENV_PATH` is used by the sample systemd units to prepend `${PYTHON_VENV_PATH}/bin` to `PATH` before launching the collector and dashboard commands.

`COLLECTOR_SINKS` is used only when no sink CLI flags are provided. Use `all` or a comma-separated list such as `mariadb,thingspeak,opensearch`.

`ALERT_CHANNELS` is used only when no alert CLI flags are provided. Use `all` or a comma-separated list such as `telegram`.

## Setup

Install from PyPI after the package is published:

```bash
pip install solar-rs485-monitor
```

For local development with `uv` and the project `.venv`:

```bash
uv venv --python 3.10 .venv
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
#SERIAL_PORT="socket://RS485_HOST_IP:9600"
```

For the current development setup, where the RS485 USB adapter is attached to a remote RS485 host and WSL connects to it over TCP:

```env
#SERIAL_PORT="/dev/ttyUSB0"
SERIAL_PORT="socket://RS485_HOST_IP:9600"
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

## Inverter/REMS Data Packet Protocol

This section summarizes the protocol currently supported by the parser for InoElectric IEPVS-3.5-G1/G2. It keeps the request frame, response frame, data payload, and `fault_code` bit interpretation in one place.

The supported protocol is the Renewable Energy Monitoring System (REMS) protocol.

Other inverter models can use different request commands, response lengths, data offsets, scaling rules, and CRC byte order. Do not assume the layout below applies to another model without checking that product's manual.

### Request Frame

The tested request frame is `7e 01 01 d1 88`.

| Byte | Example value | Meaning |
| ---: | ---: | --- |
| 0 | `0x7E` | SOP, frame start |
| 1 | `0x01` | Station number, inverter ID (`0x01`..`0xNN`) |
| 2 | `0x01` | Request command |
| 3-4 | `0xD1 0x88` | CRC16 |

### Response Frame

The default configuration expects a 33-byte response frame with a 26-byte data payload.

| Byte | Length | Meaning | Current parser validation |
| ---: | ---: | --- | --- |
| 0 | 1 | SOP, frame start | `0x7E` |
| 1 | 1 | Station number, inverter ID | Must match `INVERTER_ID` |
| 2 | 1 | Response command | `0x02` |
| 3 | 1 | Data length high byte | High byte of data length `0x001A` |
| 4 | 1 | Data length low byte | Low byte of data length `0x001A` |
| 5-30 | 26 | Data payload | Interpreted by the payload table below |
| 31-32 | 2 | CRC16 | `INVERTER_CRC_ORDER`, default `LH` |

Multi-byte values are decoded as big-endian unsigned integers. CRC is calculated as Modbus CRC16, and `LH` means low byte followed by high byte. The tested request frame and sample response frame in this project use `LH` CRC byte order.

### Response Data Layout

The official manual defines the response data in the following 26-byte payload order. The current parser uses the same order.

| Order | Manual item | Data bytes | Length | Output field | Interpretation |
| ---: | --- | ---: | ---: | --- | --- |
| 1 | PV voltage | data 0-1 | 2 byte | `input_dc_voltage_v` | DC input voltage from the PV side |
| 2 | PV current | data 2-3 | 2 byte | `input_dc_current_a` | DC input current from the PV side |
| 3 | PV output | data 4-5 | 2 byte | `input_dc_power_w` | DC input power from the PV side |
| 4 | Grid voltage | data 6-7 | 2 byte | `output_ac_voltage_v` | Grid-side AC output voltage |
| 5 | Grid current | data 8-9 | 2 byte | `output_ac_current_a` | Grid-side AC output current |
| 6 | Current output | data 10-11 | 2 byte | `output_ac_power_w` | Grid-side AC output power |
| 7 | Power factor | data 12-13 | 2 byte | `output_ac_power_factor_pct` | 0.1 scale, % |
| 8 | Frequency | data 14-15 | 2 byte | `output_ac_frequency_hz` | 0.1 scale, Hz |
| 9 | Total generation | data 16-23 | 8 byte | `total_generation_kwh` | 0.001 scale, kWh |
| 10 | Fault state | data 24-25 | 2 byte | `fault_code` | Bitmask |

### Output Field Interpretation

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
| `raw_frame_hex` | full frame | N/A | hex bytes | Raw response frame for debugging |

### fault_code Bit Interpretation

`fault_code` is a 2-byte unsigned bitmask. One response can contain more than one active bit at the same time, so do not interpret it as a single enum value.

Simple rules:

- If only one bit is active, `fault_code` equals that bit value.
- If multiple bits are active, `fault_code` is the sum of active bit values.
- Bit 0 is the operation-state bit. `1` means not operating, and `0` means operating.
- Fault-event detection uses Bit 1+.

| Bit | Mask (hex) | Value (decimal, single-bit) | Meaning (when `1`) |
| ---: | ---: | ---: | --- |
| 0 | `0x0001` | 1 | Inverter not operating |
| 1 | `0x0002` | 2 | PV over-voltage |
| 2 | `0x0004` | 4 | PV under-voltage |
| 3 | `0x0008` | 8 | PV over-current |
| 4 | `0x0010` | 16 | Inverter IGBT error |
| 5 | `0x0020` | 32 | Inverter over-temperature |
| 6 | `0x0040` | 64 | Grid over-voltage |
| 7 | `0x0080` | 128 | Grid under-voltage |
| 8 | `0x0100` | 256 | Grid over-current |
| 9 | `0x0200` | 512 | Grid over-frequency |
| 10 | `0x0400` | 1024 | Grid under-frequency |
| 11 | `0x0800` | 2048 | Islanding / blackout |
| 12 | `0x1000` | 4096 | Ground fault (leakage) |

Examples:

- `fault_code = 2`: Bit 1 only, PV over-voltage
- `fault_code = 72`: Bit 3 + Bit 6, `8 + 64`

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
solar-rs485-monitor --port socket://RS485_HOST_IP:9600
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

Send fault alert messages to Telegram:

```bash
solar-rs485-monitor --telegram
```

Write collected data to MariaDB:

```bash
solar-rs485-monitor --mariadb
```

Write collected data to Supabase (PostgreSQL):

```bash
solar-rs485-monitor --supabase
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

Repeat collection and send to Telegram:

```bash
solar-rs485-monitor --interval 60 --telegram
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
solar-rs485-monitor --interval 60 --sqlite --google-sheet --thingspeak --mariadb --supabase --opensearch
```

Or enable every configured sink with one option:

```bash
solar-rs485-monitor --loop --all-sinks
```

With `--all-sinks`, SQLite, Google Sheets, ThingSpeak, MariaDB, and Supabase are enabled. OpenSearch is enabled only when `OPENSEARCH_URL` is set. Use `--opensearch` explicitly if you want missing configuration to be reported as an error.

Or enable every configured alert channel with one option:

```bash
solar-rs485-monitor --loop --all-alerts
```

With `--all-alerts`, Telegram is enabled only when `TELEGRAM_BOT_TOKEN` and at least one target in `TELEGRAM_CHAT_IDS` are set. Use `--telegram` explicitly if you want missing configuration to be reported as an error.

External sink/alert failures are isolated. If SQLite, Google Sheets, ThingSpeak, Telegram, MariaDB, or OpenSearch fails because of a missing credential, authentication error, network error, rate limit, filesystem permission issue, or database connection issue, the collector prints an error JSON for that channel and continues the remaining work. A failed sink or alert does not stop inverter collection or block another enabled channel.

## systemd Service

A sample systemd unit is available at [packaging/systemd/solar-rs485-monitor.service](packaging/systemd/solar-rs485-monitor.service). It reads `/etc/solar-rs485-monitor.conf` via `EnvironmentFile` and builds `PATH` using `PYTHON_VENV_PATH`:

```ini
EnvironmentFile=/etc/solar-rs485-monitor.conf
ExecStart=/usr/bin/env PATH=${PYTHON_VENV_PATH}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin solar-rs485-monitor --loop
```

Before installing it, set `PYTHON_VENV_PATH` in `/etc/solar-rs485-monitor.conf` to your virtualenv root, for example `/opt/myapp/.venv`.

The service uses the normal config lookup order. Put the daemon config at `/etc/solar-rs485-monitor.conf` unless you have a specific reason to keep it next to the executable. Change `COLLECT_INTERVAL`, `COLLECTOR_SINKS`, or `ALERT_CHANNELS` in that config file to adjust daemon behavior without editing the systemd unit.

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

If you only want selected sinks in the service, replace `--all-sinks` with explicit flags such as `--sqlite` or `--sqlite --thingspeak --mariadb --opensearch`. For alerts, use `--telegram` or `--all-alerts`.

## Telegram Configuration

To use Telegram alerting (`--telegram` or `--all-alerts`), configure these values in `solar-rs485-monitor.conf`:

```env
TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_IDS=""
TELEGRAM_MESSAGE_THREAD_ID=""
TELEGRAM_TIMEOUT="5.0"
TELEGRAM_DISABLE_NOTIFICATION="false"
TELEGRAM_PARSE_MODE="Markdown"
TELEGRAM_SEND_SUMMARY="false"
TELEGRAM_SEND_FAULT_EVENT="true"
TELEGRAM_SEND_STANDBY_EVENT="false"
```

`TELEGRAM_BOT_TOKEN` is the bot API token from BotFather. `TELEGRAM_CHAT_IDS` accepts a comma-separated list of target chat/group IDs for fan-out delivery. For forum topics, set `TELEGRAM_MESSAGE_THREAD_ID`.

If multiple targets are configured, the alert attempts delivery to all of them. A failed target does not stop delivery to other targets.

By default, the alert channel skips normal measurements and sends messages only when a fault event is detected (excluding Bit 0, and triggered when any Bit 1+ is active). The fault event message includes key measurement values and active fault bits. Set `TELEGRAM_SEND_SUMMARY="true"` if you also want a summary message on each detected event.

If you want Telegram to notify inverter standby/off and normal recovery transition events, set `TELEGRAM_SEND_STANDBY_EVENT="true"`. This sends a message only when `fault_code` Bit 0 changes from `0` to `1` or `1` to `0` (transition-based), so repeated low-power nighttime samples do not spam duplicate standby messages. If Bit 1+ fault bits are active during a `1` to `0` transition, the sample is treated as a fault event instead of a normal event.

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

Open the displayed Streamlit URL in a browser. The sidebar lets you select the data source, start date, and end date. If the start and end dates are the same, the dashboard shows that single day. The end date cannot be earlier than the start date, and neither date can be in the future. The initial start and end dates are calculated from `DASHBOARD_DEFAULT_RANGE`.

The dashboard shows inverter name and ID at the top, then renders each collected metric as a separate chart. Query results are aggregated into selectable 1 minute, 2 minute, 5 minute, 10 minute, 15 minute, 30 minute, 1 hour, 3 hour, 6 hour, or 12 hour buckets before charting to reduce database transfer and browser rendering cost. The minimum selectable bucket is raised dynamically by selected date range and `DASHBOARD_MAX_POINTS` so oversized result sets are avoided. Total and daily generation charts display at least 14 days relative to the selected end date, and weekly generation displays at least 16 weeks. Monthly and yearly generation charts use their own fixed config-only windows, defaulting to 12 months and 10 years.

Dashboard server options are read from `DASHBOARD_SERVER_ADDRESS`, `DASHBOARD_SERVER_PORT`, `DASHBOARD_SERVER_HEADLESS`, `DASHBOARD_GATHER_USAGE_STATS`, and `DASHBOARD_RUN_ON_SAVE` in `solar-rs485-monitor.conf`. The default sidebar auto-refresh option can be set with `DASHBOARD_AUTO_REFRESH_SECONDS`, and users can still change it from the sidebar while running. The selected interval refreshes the dashboard content area without reloading the browser page. To override Streamlit server options from the command line:

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
MARIADB_HOST="YOUR_MARIADB_HOST"
MARIADB_PORT="3306"
MARIADB_USER="solar_logger"
MARIADB_PASSWORD="YOUR_MARIADB_PASSWORD"
MARIADB_DATABASE="solar_rs485_monitor"
MARIADB_TABLE="inverter_log"
MARIADB_CONNECT_TIMEOUT="5.0"
```

The MariaDB sink now creates the target table automatically when it does not exist, including timestamp, inverter_id, and fault_code indexes. It inserts only the parsed metric fields defined by the current sink schema; `raw_frame_hex` is printed in JSON for debugging but is not stored in MariaDB unless the table and sink are extended.

The selected database must already exist and the logging user needs permissions to create tables and indexes on first run.

The database user only needs `INSERT` for normal logging. `SELECT` can be useful for verification and dashboards.

Example MariaDB schema and logging user (optional pre-provisioning):

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
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'DB insert time',
    INDEX idx_timestamp (timestamp),
    INDEX idx_inverter_id (inverter_id),
    INDEX idx_fault_code (fault_code)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COMMENT='solar-rs485-monitor inverter log';

CREATE USER 'solar_logger'@'%' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT INSERT, SELECT ON solar_rs485_monitor.inverter_log TO 'solar_logger'@'%';

FLUSH PRIVILEGES;
```

The `%` host allows remote access from any IP. For production, restrict it to the collector host IP whenever possible.

## Supabase (PostgreSQL) Configuration

To use `--supabase`, configure these values in `solar-rs485-monitor.conf`:

```env
SUPABASE_HOST="YOUR_SUPABASE_HOST"
SUPABASE_PORT="5432"
SUPABASE_USER="YOUR_SUPABASE_USER"
SUPABASE_PASSWORD="YOUR_SUPABASE_PASSWORD"
SUPABASE_DATABASE="postgres"
SUPABASE_SCHEMA="public"
SUPABASE_TABLE="inverter_log"
SUPABASE_CONNECT_TIMEOUT="5.0"
```

Notes:

- If the Direct Connection for your Supabase project requires IPv6, IPv4-only clients must use the Session Pooler. In that case, use the pooler host and pooler username. Example:
  - host: `aws-1-<region>.pooler.supabase.com` (e.g. `aws-1-ap-northeast-2.pooler.supabase.com`)
  - user: `postgres.<project_ref>` (e.g. `postgres.jupglvkymeilpprzjxmv`)
  - database: `postgres`
  - port: `5432`
- The Supabase sink automatically creates the target schema, table, and indexes if they do not exist. It inserts all parsed metrics including `raw_frame_hex`.
- The database itself must already exist (the default is `postgres`); the logging user needs permission to create objects on first run.

Example PostgreSQL schema that the sink auto-creates (for reference):

```sql
CREATE SCHEMA IF NOT EXISTS "public";

CREATE TABLE IF NOT EXISTS "public"."inverter_log" (
    id BIGSERIAL PRIMARY KEY,
    "timestamp" TIMESTAMPTZ NOT NULL,
    inverter_name TEXT NOT NULL,
    inverter_id INTEGER NOT NULL,
    input_dc_voltage_v INTEGER,
    input_dc_current_a DOUBLE PRECISION,
    input_dc_power_w INTEGER,
    output_ac_voltage_v INTEGER,
    output_ac_current_a DOUBLE PRECISION,
    output_ac_power_w INTEGER,
    output_ac_power_factor_pct DOUBLE PRECISION,
    output_ac_frequency_hz DOUBLE PRECISION,
    total_generation_kwh DOUBLE PRECISION,
    fault_code INTEGER DEFAULT 0,
    raw_frame_hex TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inverter_log_timestamp
  ON "public"."inverter_log" ("timestamp");
CREATE INDEX IF NOT EXISTS idx_inverter_log_inverter_id
  ON "public"."inverter_log" (inverter_id);
CREATE INDEX IF NOT EXISTS idx_inverter_log_fault_code
  ON "public"."inverter_log" (fault_code);
```

Run with:

```bash
solar-rs485-monitor --supabase
```

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
GOOGLE_SHEET_FILE_NAME="YOUR_GOOGLE_SHEET_FILE_NAME"
GOOGLE_WORKSHEET_NAME=""
```

`GOOGLE_SHEET_FILE_NAME` is treated as a base name. Runtime writes to yearly spreadsheets named `<GOOGLE_SHEET_FILE_NAME>-YYYY` (for example, `Solar-RS485-Monitor-2026`).

For each yearly spreadsheet, monthly worksheets `YYYY-01` through `YYYY-12` are managed automatically. Missing monthly worksheets are created automatically, and data is written to the worksheet for the current collection month.

`GOOGLE_WORKSHEET_NAME` is kept only for backward compatibility and is no longer used to control worksheet rotation.

Also provide the Google service account fields from `solar-rs485-monitor.conf.template`.

The spreadsheet must be shared with the service account email:

```env
GOOGLE_CLIENT_EMAIL="service-account@your-project-id.iam.gserviceaccount.com"
```

The collector creates the header row automatically if the worksheet is empty. If row 1 already exists and does not match the expected schema, the script stops with a header mismatch error.

## Output

The script prints one JSON object per collection attempt.

Output fields and `fault_code` bit interpretation are collected in [Inverter/REMS Data Packet Protocol](#inverterrems-data-packet-protocol).

Successful reads include fields such as:

```json
{
  "@timestamp": "2026-07-01T10:16:13.844550+00:00",
  "inverter_name": "Inoelectric IEPVS-3.5-G1",
  "inverter_id": 1,
  "input_dc_voltage_v": 193,
  "input_dc_current_a": 0,
  "input_dc_power_w": 54,
  "output_ac_voltage_v": 229,
  "output_ac_current_a": 0,
  "output_ac_power_w": 37,
  "output_ac_power_factor_pct": 85.0,
  "output_ac_frequency_hz": 60.0,
  "total_generation_kwh": 112.244,
  "fault_code": 0,
  "raw_frame_hex": "7e 01 02 00 1a 00 c1 00 00 00 36 00 e5 00 00 00 25 03 52 02 58 00 00 00 00 00 01 b6 74 00 00 7c 21"
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
- `SUPABASE_PASSWORD is not set` or `SUPABASE_* is not set`: set the required Supabase fields in `solar-rs485-monitor.conf` before running with `--supabase`.
- `Supabase logging failed` or `failed to resolve host ... No address associated with hostname`: if your Supabase Direct Connection requires IPv6, use the Session Pooler host and pooler username (e.g. `aws-1-<region>.pooler.supabase.com`, `postgres.<project_ref>`). Also verify host, port, firewall rules, username, password, database, schema, and table.
- `psycopg is required for Supabase logging`: install project dependencies so that the `psycopg` package is available.
- `SQLite unable to open database file`: check `SQLITE_PATH` and directory write permissions.
- `OPENSEARCH_URL is not set`: set the OpenSearch endpoint before running with `--opensearch`.
- `OpenSearch request failed`: check the endpoint, index permission, username, password, TLS setting, and cluster network access.
- `Telegram request failed`: check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS`, bot permissions in the target group, and outbound network access to `api.telegram.org`.
- `Google Sheet not found or access denied`: share the spreadsheet with `GOOGLE_CLIENT_EMAIL`.
- `Google worksheet header mismatch`: check that row 1 header columns match the expected schema.
