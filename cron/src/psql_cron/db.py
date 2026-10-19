"""Database connection and query execution for psql_cron."""

import logging
import re
import os

import pg8000.dbapi
from psql_cron.config import DB_HOST, DB_PASSWORD, DB_PORT, DB_USER, SyncConfig
from shared.pgsecurity import build_ssl_context, parse_allowlist, table_allowed

logger = logging.getLogger("psql_cron.db")

DB_SSL_CONTEXT = build_ssl_context(
    os.getenv("DB_SSLMODE", "require"), os.getenv("DB_SSLROOTCERT", "")
)

# Access control allowlists: empty / '*' means unrestricted (same rule as the bridge).
ALLOWED_DATABASES = parse_allowlist("CRON_ALLOWED_DATABASES")
ALLOWED_SCHEMAS = parse_allowlist("CRON_ALLOWED_SCHEMAS")
ALLOWED_TABLES = parse_allowlist("CRON_ALLOWED_TABLES")


def check_scope(config: SyncConfig) -> str | None:
    """Returns an error message if the sync's database or schema is not allowed, else None."""
    if ALLOWED_DATABASES and config.database.lower() not in ALLOWED_DATABASES:
        return f"Access to database '{config.database}' is not allowed."
    if ALLOWED_SCHEMAS and config.schema.lower() not in ALLOWED_SCHEMAS:
        return f"Access to schema '{config.schema}' is not allowed."
    return None


def filter_allowed_tables(config: SyncConfig, tables: list[str]) -> tuple[list[str], list[str]]:
    """Splits tables into (allowed, denied) according to the table allowlist."""
    allowed = [t for t in tables if table_allowed(ALLOWED_TABLES, config.schema, t)]
    denied = [t for t in tables if t not in allowed]
    return allowed, denied


def clean_whitespace(val):
    """Collapse any sequence of whitespace characters into a single space and strip."""
    if isinstance(val, str):
        return re.sub(r"\s+", " ", val).strip()
    return val


def get_connection(config: SyncConfig):
    """Creates a new pg8000 database connection using the provided configuration."""
    return pg8000.dbapi.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=config.database,
        ssl_context=DB_SSL_CONTEXT,
    )


def fetch_schema_tables(
    config: SyncConfig,
    conn: pg8000.dbapi.Connection | None = None,
) -> list[str]:
    """
    Retrieves all table and view names from the configured schema in PostgreSQL.
    Excludes system tables and filters by SELECT privilege.
    """
    should_close = False
    if conn is None:
        conn = get_connection(config)
        should_close = True

    try:
        cursor = conn.cursor()
        relkinds = ("'r'", "'v'", "'m'", "'p'") if config.include_views else ("'r'", "'p'")
        relkinds_filter = ", ".join(relkinds)

        query = f"""
            SELECT c.relname
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relkind IN ({relkinds_filter})
              AND has_table_privilege(c.oid, 'SELECT')
            ORDER BY c.relname;
        """
        logger.debug(f"[{config.syncname}] Fetching tables from schema '{config.schema}'")
        cursor.execute(query, (config.schema,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.warning(
            f"[{config.syncname}] Primary schema query failed ({e}), attempting information_schema fallback..."
        )
        try:
            types = ("'BASE TABLE'", "'VIEW'") if config.include_views else ("'BASE TABLE'",)
            fallback_query = f"""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type IN ({', '.join(types)})
                ORDER BY table_name;
            """
            cursor.execute(fallback_query, (config.schema,))
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as fallback_e:
            logger.error(f"[{config.syncname}] Fallback schema query failed: {fallback_e}")
            raise e
    finally:
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass


def fetch_table_data(
    config: SyncConfig,
    table_name: str | None = None,
    conn: pg8000.dbapi.Connection | None = None,
) -> tuple[list[str], list[tuple]]:
    """
    Connects to the PostgreSQL database and retrieves all rows from the configured table/view.
    Returns (columns, cleaned_rows).
    """
    target_table = table_name or config.table
    should_close = False
    if conn is None:
        conn = get_connection(config)
        should_close = True

    try:
        cursor = conn.cursor()

        # Safely quote schema and table identifiers
        escaped_schema = config.schema.replace('"', '""')
        escaped_table = target_table.replace('"', '""')
        sql_query = f'SELECT * FROM "{escaped_schema}"."{escaped_table}";'

        logger.debug(f"[{config.syncname}] Executing query: {sql_query}")
        cursor.execute(sql_query)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        raw_rows = cursor.fetchall()

        cleaned_rows = [
            tuple(clean_whitespace(val) for val in row)
            for row in raw_rows
        ]
        return columns, cleaned_rows

    finally:
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass
