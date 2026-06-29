# Copilot Instructions for Solar-RS485-Monitor

## Project Overview
- This is a Python package for collecting solar inverter metrics over RS485 serial communication.
- The package entry point is `solar-rs485-monitor`, defined in `pyproject.toml`.
- Runtime code lives under `src/solar_rs485_monitor/`.
- The main collector implementation is `src/solar_rs485_monitor/collector.py`.

## Language Guidelines
- Use English for code, identifiers, comments, commit messages, and primary documentation unless the user asks otherwise.
- Keep `README.md` as the English documentation and `README.ko.md` as the Korean documentation.
- When changing user-facing documentation, keep both README files aligned in content and structure.
- Respond to the user in Korean unless they explicitly request another language.

## Configuration
- Runtime configuration is loaded from `.env` with `python-dotenv`.
- `.env.template` and `.env` should keep the same structure and key order.
- `.env.template` contains placeholders and safe examples.
- `.env` contains local real values and must not be committed.
- Serial access is selected through `SERIAL_PORT`.
  - Local USB example: `/dev/ttyUSB0`
  - TCP-forwarded RS485 host example: `socket://RS485_HOST_IP:9600`

## Protocol Scope
- The parser is written and tested for InoElectric IEPVS-3.5-G1/G2.
- Do not assume another inverter model has the same request frame, response length, byte offsets, scaling, CRC order, or metric meanings.
- For other products, update `INVERTER_REQUEST_HEX` and the response parsing logic based on that product's specification or manual.

## Packaging
- This project is intended to be publishable to PyPI.
- Build metadata is in `pyproject.toml`.
- Source distribution and wheel can be built with `uv build` or `python -m build`.
- Do not reintroduce the removed root-level `inverter_collector.py`; use the console script entry point instead.

## Validation
- Prefer focused validation after changes:
  - `uv pip install --python .venv/bin/python -e .`
  - `.venv/bin/solar-rs485-monitor --help`
  - `uv build`
- Hardware communication cannot be validated without the RS485 adapter and inverter.
