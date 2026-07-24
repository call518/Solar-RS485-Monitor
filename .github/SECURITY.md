# Security Policy

## Supported Versions

Security fixes are provided for the latest released version of
`solar-rs485-monitor`.

Older versions may not receive patches unless the issue is severe and the fix is
small enough to backport safely.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public GitHub issues.

Use GitHub's private vulnerability reporting or open a private security advisory
for this repository when available. Include:

- A clear description of the vulnerability
- Steps to reproduce the issue
- The affected version
- Relevant configuration details, with secrets removed
- Any known impact or workaround

If private reporting is not available, contact the repository maintainer through
GitHub and avoid posting exploit details publicly.

## Secrets and Credentials

Never include real credentials in reports, logs, screenshots, or sample config
files. This project can use credentials such as:

- `TELEGRAM_BOT_TOKEN`
- Google Sheets service account credentials
- Database passwords
- Supabase keys
- OpenSearch credentials
- ThingSpeak API keys

If a secret was exposed, revoke and rotate it before sharing diagnostic details.

## Scope

Security-sensitive areas include:

- Credential handling and configuration loading
- Telegram alert delivery
- Database and external sink integrations
- Dashboard authentication and cookies
- Packaging and release workflows

Hardware behavior, inverter faults, RS485 wiring, and local network availability
are operational issues unless they expose a software vulnerability.
