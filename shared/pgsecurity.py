"""Connection security shared by the bridge and the cron exporter: TLS context and access allowlists."""

import os
import ssl


def build_ssl_context(sslmode: str, sslrootcert: str = ""):
    """
    Build the TLS context for pg8000 following libpq sslmode semantics:
    - disable:     plain TCP, no TLS
    - require:     TLS, but the server certificate is not verified
    - verify-ca:   TLS, certificate must chain to sslrootcert (or system CAs)
    - verify-full: verify-ca plus the certificate must match the DB host
    """
    sslmode = sslmode.strip().lower()
    sslrootcert = sslrootcert.strip()
    if sslmode == 'disable':
        return False  # pg8000 treats None as "try TLS", so False is needed to force plain TCP
    if sslmode == 'require':
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if sslmode in ('verify-ca', 'verify-full'):
        ctx = ssl.create_default_context(cafile=sslrootcert or None)
        ctx.check_hostname = sslmode == 'verify-full'
        return ctx
    raise ValueError(f"Unsupported DB_SSLMODE '{sslmode}'. Use disable, require, verify-ca or verify-full.")


def parse_allowlist(*keys):
    """
    Parse a comma-separated allowlist from the first of `keys` declared in the environment.
    If not declared, empty, '*', or 'all', access is unrestricted (returns an empty set).
    """
    for key in keys:
        if key in os.environ:
            raw = os.environ[key].strip()
            if not raw or raw in ('*', 'all'):
                return set()
            items = [item.strip().lower() for item in raw.split(',') if item.strip()]
            if '*' in items or 'all' in items:
                return set()
            if items:
                return set(items)
    return set()


def table_allowed(allowed_tables: set, schema: str, table: str) -> bool:
    """A table matches the allowlist by bare name or as 'schema.table'. Empty allowlist allows all."""
    table, schema = table.lower(), schema.lower()
    return not allowed_tables or table in allowed_tables or f"{schema}.{table}" in allowed_tables
