# Solar-RS485-Monitor

Solar inverter monitoring script for RS485/serial communication.

The collector reads inverter data, prints the parsed result as JSON, and can optionally write the result to external logging sinks.

Optional logging sinks are implemented as separate modules under `src/solar_rs485_monitor/sinks/`. This keeps inverter collection separate from external logging integrations such as Google Sheets, ThingSpeak, MariaDB, and future sinks like OpenSearch or Elasticsearch.

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

Collect once and print JSON:

```bash
solar-rs485-monitor
```

Override the port temporarily from the command line:

```bash
solar-rs485-monitor --port socket://192.168.35.6:9600
```

Repeat collection every 60 seconds:

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

Multiple sinks can be enabled together:

```bash
solar-rs485-monitor --interval 60 --google-sheet --thingspeak --mariadb
```

Or enable every configured sink with one option:

```bash
solar-rs485-monitor --interval 60 --all-sinks
```

External logging failures are isolated. If Google Sheets, ThingSpeak, or MariaDB fails because of a missing credential, authentication error, network error, rate limit, or database connection issue, the collector prints an error JSON for that sink and continues the remaining work. A failed sink does not stop inverter collection or block another enabled sink.

## systemd Service

A sample systemd unit is available at [packaging/systemd/solar-rs485-monitor.service](packaging/systemd/solar-rs485-monitor.service). It runs the collector every 60 seconds and enables all sinks:

```ini
ExecStart=/usr/bin/env solar-rs485-monitor --interval 60 --all-sinks
```

Before installing it, edit this setting for the target host:

- `Environment=PATH=...`: include the directory that contains the installed `solar-rs485-monitor` command. Check it with `which solar-rs485-monitor`.

The service uses the normal config lookup order. Put the daemon config at `/etc/solar-rs485-monitor.conf` unless you have a specific reason to keep it next to the executable.

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

If you only want selected sinks in the service, replace `--all-sinks` with explicit flags such as `--mariadb` or `--thingspeak --mariadb`.

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
| `field1` | `pv_voltage_v` |
| `field2` | `pv_current_a` |
| `field3` | `pv_power_w` |
| `field4` | `grid_voltage_v` |
| `field5` | `grid_current_a` |
| `field6` | `current_output_w` |
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
| `@timestamp` | N/A | N/A | ISO 8601 UTC | Collection timestamp generated by the collector |
| `inverter_name` | N/A | N/A | text | Name from `INVERTER_NAME` |
| `inverter_id` | frame byte 1 | 1 | numeric ID | Inverter ID returned by the device |
| `pv_voltage_v` | data 0-1 | 1 | V | PV input voltage |
| `pv_current_a` | data 2-3 | 1 | A | PV input current |
| `pv_power_w` | data 4-5 | 1 | W | PV input power |
| `grid_voltage_v` | data 6-7 | 1 | V | Grid voltage |
| `grid_current_a` | data 8-9 | 1 | A | Grid current |
| `current_output_w` | data 10-11 | 1 | W | Current AC output power |
| `power_factor_pct` | data 12-13 | 0.1 | % | Power factor percentage |
| `frequency_hz` | data 14-15 | 0.1 | Hz | Grid frequency |
| `total_generation_kwh` | data 16-23 | 0.001 | kWh | Total accumulated generation |
| `fault_code` | data 24-25 | 1 | code | Raw fault code |
| `fault` | derived from `fault_code` | N/A | boolean | `true` when `fault_code != 0` |
| `raw_frame_hex` | full frame | N/A | hex bytes | Raw response frame for debugging |

Successful reads include fields such as:

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
- `Google Sheet not found or access denied`: share the spreadsheet with `GOOGLE_CLIENT_EMAIL`.
- `Google worksheet not found`: create the worksheet tab or fix `GOOGLE_WORKSHEET_NAME`.
