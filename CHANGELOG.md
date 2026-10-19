# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-19

Initial release.

### Added
- **postgres-bridge**: driverless PostgreSQL bridge for Excel. A Flask/Gunicorn service bound to
  `127.0.0.1:13714` with `/query` (JSON), `/csv` (Excel-friendly CSV with BOM) and `/health` endpoints.
- Read-only query enforcement (`SELECT`/`WITH` only, no stacked statements, destructive keywords blocked).
- Whitespace normalization of string values in all exports.
- Access control allowlists for databases, schemas and tables (`ALLOWED_*`, with `database`/`schema`/`tables` aliases).
- TLS to PostgreSQL with libpq-style `DB_SSLMODE` (`disable`, `require`, `verify-ca`, `verify-full`) and `DB_SSLROOTCERT`.
- **psql-cron**: scheduled exporter of tables/views to JSON/CSV driven by one `.ini` file per sync,
  with multiple cron schedules per sync, hot reload of sync files, atomic output writes, `--once` and `--sync` modes.
- Enforcement of TLS and `CRON_ALLOWED_DATABASES/SCHEMAS/TABLES` allowlists in psql-cron, with dedicated
  credentials (`CRON_DB_USER`, `CRON_DB_PASSWORD`); connection settings cannot be set from `.ini` files.
- Hardened psql-cron container: read-only root filesystem, all capabilities dropped, `no-new-privileges`,
  no published ports, read-only syncs mount and a single writable export folder (`CRON_EXPORT_DIR`).
- Shared `shared/pgsecurity.py` (TLS context and allowlist parsing) used by both services.
- Single `docker-compose.yml` and `.env` for both services.
