"""Configuration parser and data models for psql_cron."""

import configparser
import dataclasses
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("psql_cron.config")


# Environment Defaults
# Connection settings come only from the environment (never from .ini files).
# The cron exporter uses its own credentials, separate from the bridge's.
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("CRON_DB_USER", "")
DB_PASSWORD = os.getenv("CRON_DB_PASSWORD", "")
DEFAULT_SYNCS_DIR = os.getenv("SYNCS_DIR", "/app/syncs" if os.path.exists("/app/syncs") else "./syncs")
DEFAULT_OUTPUT_DIR = os.getenv("DEFAULT_OUTPUT_DIR") or os.getenv("OUTPUT_DIR") or ("/app/output" if os.path.exists("/app/output") else "./output")
DEFAULT_CRON_SCHEDULE = os.getenv("DEFAULT_CRON_SCHEDULE", os.getenv("CRON_SCHEDULE", "0 * * * *"))
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "true").lower() in ("true", "1", "yes")
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in ("true", "1", "yes")


@dataclasses.dataclass
class SyncConfig:
    syncname: str
    database: str
    schema: str
    table: str
    csv: bool
    json: bool
    output_path: Path
    cron_schedules: list[str] = dataclasses.field(default_factory=list)
    exclude_tables: list[str] = dataclasses.field(default_factory=list)
    include_views: bool = True

    @property
    def cron(self) -> str:
        """Returns primary or first cron schedule for backwards compatibility."""
        return self.cron_schedules[0] if self.cron_schedules else DEFAULT_CRON_SCHEDULE

    @property
    def is_all_tables(self) -> bool:
        """Returns True if configured to export all tables in the schema."""
        return self.table.strip().lower() in ("*", "all", "%")

    def get_target_tables(self) -> list[str]:
        """Returns list of specific tables if configured as a list, or single table."""
        if self.is_all_tables:
            return []
        return [t.strip() for t in self.table.split(",") if t.strip()]


def parse_ini_file(filepath: Path) -> SyncConfig | None:
    """
    Parses a synchronization .ini file.
    Supports INI files with or without section headers.
    Supports multiple cron schedules via cron.<n> (e.g. cron.1, cron.2) as well as cron.
    Returns SyncConfig or None if invalid.
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read file {filepath}: {e}")
        return None

    # If the file does not begin with a section header [section], wrap it in [sync]
    if not re.search(r"^\s*\[.+\]", content, re.MULTILINE):
        content = f"[sync]\n{content}"

    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    try:
        parser.read_string(content)
    except Exception as e:
        logger.error(f"Error parsing INI content in {filepath.name}: {e}")
        return None

    section_name = parser.sections()[0] if parser.sections() else "sync"
    section = parser[section_name]

    # Required and optional properties
    database = section.get("database", "").strip().strip("'\"")
    schema = (section.get("schema", "public").strip() or "public").strip("'\"")
    table = section.get("table", section.get("tables", "")).strip().strip("'\"")
    raw_output_path = section.get("output_path", "").strip().strip("'\"")

    # If table is not specified or empty, default to '*' (all tables/views in the schema)
    if not table:
        logger.info(f"[{filepath.name}] 'table' not specified; defaulting to '*' (all tables in schema '{schema}')")
        table = "*"

    # Excluded tables (optional)
    raw_exclude = section.get("exclude_tables", section.get("ignore_tables", "")).strip().strip("'\"")
    exclude_tables = [t.strip() for t in raw_exclude.split(",") if t.strip()]

    # Include views (optional, defaults to True)
    include_views = True
    try:
        include_views = section.getboolean("include_views", fallback=True)
    except ValueError:
        raw_iv = section.get("include_views", "").strip().lower()
        if raw_iv:
            include_views = raw_iv in ("true", "1", "yes", "t", "y")

    # Parse cron schedules: supports cron, cron.1, cron.2, etc.
    cron_schedules: list[str] = []
    # Collect items matching cron or cron.<n>
    cron_matches = [
        (k.strip().lower(), v.strip().strip("'\""))
        for k, v in section.items()
        if re.match(r"^(?:cron|schedule|cron_schedule)(?:\.[0-9a-zA-Z_-]+)?$", k.strip().lower())
    ]
    # Sort so cron.1, cron.2 etc. appear in order
    cron_matches.sort(key=lambda item: item[0])

    for _, val in cron_matches:
        if val and val not in cron_schedules:
            cron_schedules.append(val)

    if not cron_schedules:
        cron_schedules = [DEFAULT_CRON_SCHEDULE]

    # Parse booleans
    csv_enabled = False
    json_enabled = False
    try:
        csv_enabled = section.getboolean("csv", fallback=False)
    except ValueError:
        raw_val = section.get("csv", "").strip().lower()
        csv_enabled = raw_val in ("true", "1", "yes", "t", "y")

    try:
        json_enabled = section.getboolean("json", fallback=False)
    except ValueError:
        raw_val = section.get("json", "").strip().lower()
        json_enabled = raw_val in ("true", "1", "yes", "t", "y")

    # Validation
    if not database:
        logger.error(f"[{filepath.name}] Missing required field: 'database'")
        return None
    if not raw_output_path:
        logger.warning(f"[{filepath.name}] 'output_path' not specified, defaulting to: {DEFAULT_OUTPUT_DIR}")
        raw_output_path = DEFAULT_OUTPUT_DIR

    if not csv_enabled and not json_enabled:
        logger.warning(f"[{filepath.name}] Neither 'csv' nor 'json' is enabled (both are false). Nothing to export.")
        return None

    output_path = Path(raw_output_path)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    return SyncConfig(
        syncname=filepath.stem,
        database=database,
        schema=schema,
        table=table,
        csv=csv_enabled,
        json=json_enabled,
        output_path=output_path,
        cron_schedules=cron_schedules,
        exclude_tables=exclude_tables,
        include_views=include_views,
    )


def find_all_sync_configs(syncs_dir: Path, target_sync: str | None = None) -> list[SyncConfig]:
    """Finds and parses all .ini configuration files in the given directory."""
    if not syncs_dir.exists():
        logger.warning(f"Syncs directory '{syncs_dir}' does not exist. Creating it.")
        syncs_dir.mkdir(parents=True, exist_ok=True)
        return []

    ini_files = sorted(syncs_dir.glob("*.ini"))
    configs: list[SyncConfig] = []

    for ini_file in ini_files:
        if target_sync and ini_file.stem != target_sync:
            continue
        cfg = parse_ini_file(ini_file)
        if cfg is not None:
            configs.append(cfg)

    return configs
