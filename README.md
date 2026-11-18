# PostgreSQL Bridge + Cron Exporter (WSL2)

This repository runs two independent Docker services against the same PostgreSQL server:

| Service | Folder | Purpose |
|---|---|---|
| `postgres-bridge` | `bridge/` | HTTP service for Excel (`127.0.0.1:13714`), described below |
| `psql-cron` | `cron/` | Scheduled export of tables/views to JSON/CSV from `.ini` files in `cron/syncs/` |

Current version: **1.0.0** (see [CHANGELOG.md](CHANGELOG.md)).

`shared/pgsecurity.py` holds the TLS and allowlist logic used by both. Both share the one `.env`
(see `.env.example`) and the `certs/` folder; `docker compose up -d --build` starts both.

**psql-cron security** (same standard as the bridge): TLS via `DB_SSLMODE`/`DB_SSLROOTCERT`; allowlists
`CRON_ALLOWED_DATABASES/SCHEMAS/TABLES` (separate from the bridge's `ALLOWED_*`, since the two read different
schemas) are enforced on every sync; dedicated credentials `CRON_DB_USER/CRON_DB_PASSWORD`; connection settings
cannot be overridden from `.ini` files; read-only root filesystem, all capabilities dropped, no ports, `syncs/`
mounted read-only, and the only writable host folders are `CRON_EXPORT_DIR` and the optional `CRON_EXPORT_DIR_2`
(each `output_path` in a `.ini` must be inside one of them).

---

## WSL2 Driverless PostgreSQL Connection Bridge

The `bridge/` service is a lightweight Python web service running inside Docker (WSL2 Fedora 44) that allows Excel on your Windows host to query a remote PostgreSQL database **without installing any database drivers** on Windows.

## Architecture

```
[ Excel (Windows Host) ]
         │
         ▼ (HTTP GET http://localhost:13714/csv?db=...&sql=...)
[ Docker / Python Web Service (WSL2) ]
         │
         ▼ (PostgreSQL connection over TLS via pg8000)
[ PostgreSQL Server (your-db-host.example.com:5432) ]
```

- **Local Web Service Port**: `13714` (bound strictly to `127.0.0.1` for security)
- **Remote Host**: `your-db-host.example.com`
- **Remote Port**: `5432`

---

## How to Run

1. **Verify `.env`**: Make sure the `.env` file contains your target database connection details:
   ```env
   DB_HOST=your-db-host.example.com
   DB_PORT=5432
   DB_READONLY_USER=your_readonly_user
   DB_READONLY_PASSWORD=your_password

   # TLS: disable | require | verify-ca | verify-full
   DB_SSLMODE=require
   DB_SSLROOTCERT=

   # Access control allowlists (comma-separated, leave blank or omit to allow any)
   ALLOWED_DATABASES=my_database
   ALLOWED_SCHEMAS=public
   ALLOWED_TABLES=

   # Convenience aliases
   database=my_database
   schema=public

   # psql-cron exporter (see the psql-cron section below)
   CRON_DB_USER=your_cron_readonly_user
   CRON_DB_PASSWORD=your_cron_password
   CRON_ALLOWED_DATABASES=my_database
   CRON_ALLOWED_SCHEMAS=my_schema
   CRON_ALLOWED_TABLES=
   CRON_EXPORT_DIR="/mnt/c/path/to/export folder"
   # Optional second export folder (leave empty if not needed)
   CRON_EXPORT_DIR_2=
   ```

   **TLS**: connections to the database are encrypted by default (`DB_SSLMODE=require`), which does not verify the server certificate. To also verify it (recommended), save the server's certificate to `./certs/server.crt` (mounted read-only at `/certs` by `docker-compose.yml`) and set:
   ```env
   DB_SSLMODE=verify-ca          # or verify-full if the cert matches DB_HOST
   DB_SSLROOTCERT=/certs/server.crt
   ```

2. **Start the services**:
   Run the following command to build the images and start both containers in the background
   (use `docker compose up -d --build postgres-bridge` to start only the bridge):
   ```bash
   docker compose up -d --build
   ```

3. **Check container status**:
   ```bash
   docker compose ps
   ```

4. **Stop the services**:
   ```bash
   docker compose down
   ```

---

## Web API Endpoints

The service runs at `http://localhost:13714` and offers two query endpoints. Both endpoints accept the following query parameters:
* `db`: The name of the database to query.
* `sql`: The SQL SELECT or WITH query to execute.

### 1. JSON Endpoint (`/query`)
Executes the SQL query and returns results in JSON format.
* **Example URL**: `http://localhost:13714/query?db=my_database&sql=SELECT+*+FROM+users+LIMIT+10`

### 2. CSV Endpoint (`/csv`)
Executes the SQL query and returns results as a downloadable CSV file. This is the **most recommended** endpoint for Excel as Excel handles CSV import natively.
* **Example URL**: `http://localhost:13714/csv?db=my_database&sql=SELECT+*+FROM+users+LIMIT+10`

*Note: For security, only read-only queries (`SELECT` or `WITH`) are allowed. Destructive statements like `DROP`, `DELETE`, or query stacking via multiple semicolons are automatically blocked.*

### Automatic Data Cleaning
To ensure that exported data remains clean and well-formatted (especially for CSV import into Excel), all string/text fields retrieved from the database undergo automatic whitespace cleaning. Any sequence of whitespace characters (including spaces, tabs, and newlines) is collapsed into a single space, and leading/trailing whitespace is stripped.

---

## Loading Data into Excel (Zero Drivers Required)

Since WSL2 mirrors `localhost` to the Windows host, you can fetch data directly via Excel's native web data import:

### Importing as CSV (Recommended)

1. Open Excel on Windows.
2. Go to the **Data** tab -> **From Web** (in the "Get & Transform Data" section).
3. Select **Basic** and paste your query URL. For example:
   ```http
   http://localhost:13714/csv?db=your_database_name&sql=SELECT * FROM your_table LIMIT 100
   ```
   *(Make sure to URL-encode any special characters in the query parameter, or let Excel's import wizard handle it automatically).*
4. Click **OK**.
5. Excel will connect, fetch the CSV, and show a preview.
6. Click **Load** to import the query results directly into your spreadsheet!

---

## psql-cron (Scheduled Exports)

`psql-cron` reads every `*.ini` file in `cron/syncs/` (one file = one sync, named `<syncname>.ini`), exports the
selected tables/views to JSON and/or CSV, and repeats on the schedule(s) in the file. Files are picked up or
removed without restarting the container. String values get the same whitespace cleaning as the bridge.

### Sync file reference

```ini
database = my_database
schema = my_schema
table = *                      # '*' or empty = all tables/views; or "t1, t2" for specific ones
# exclude_tables = audit_log   # only used with table = *
# include_views = true         # default true

json = true
csv = false

output_path = /mnt/c/path/to/export folder   # must be inside CRON_EXPORT_DIR or CRON_EXPORT_DIR_2; defaults to DEFAULT_OUTPUT_DIR

# One or more cron schedules; the sync runs when ANY of them fires
cron.1 = 9,39 7-20 * * 1-5
cron.2 = 30 6 * * 1
```

See `cron/syncs/example.ini.template`. Output files are named `<table>.json` / `<table>.csv` (or
`<syncname>.*` for a single-table sync) and are replaced atomically.

### Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `CRON_DB_USER`, `CRON_DB_PASSWORD` | Credentials for the exporter (separate from the bridge's `DB_READONLY_*`). Connection settings can **not** be set in `.ini` files. |
| `DB_HOST`, `DB_PORT`, `DB_SSLMODE`, `DB_SSLROOTCERT` | Shared with the bridge; TLS works exactly as described above. |
| `CRON_ALLOWED_DATABASES`, `CRON_ALLOWED_SCHEMAS`, `CRON_ALLOWED_TABLES` | Same rule as the bridge's allowlists (empty or `*` = unrestricted). A sync outside them is refused; with `table = *`, tables outside `CRON_ALLOWED_TABLES` are skipped. Tables match by name or `schema.table`. |
| `CRON_EXPORT_DIR` | Host folder mounted read-write into the container at the same path. Together with `CRON_EXPORT_DIR_2` it is the only writable host location, so `output_path` values must be inside one of them. |
| `CRON_EXPORT_DIR_2` | Optional second export folder, mounted the same way. Leave empty if one folder is enough (it then falls back to `cron/output/`). Changing either folder requires recreating the container: `docker compose up -d psql-cron`. |
| `DEFAULT_CRON_SCHEDULE` | Used when a sync defines no `cron`. |
| `DEFAULT_OUTPUT_DIR` | Used when a sync defines no `output_path` (default `/app/output`, i.e. `cron/output/`). |
| `RUN_ON_STARTUP`, `RUN_ONCE` | Run all syncs at start; run once and exit. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, ... |

### Operating it

```bash
docker compose logs -f psql-cron                       # watch syncs
docker compose run --rm psql-cron psql-cron --once     # run every sync once now
docker compose run --rm psql-cron psql-cron --once --sync <syncname>   # run a single sync
```

Container hardening: read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, no published
ports, `cron/syncs/` mounted read-only.
