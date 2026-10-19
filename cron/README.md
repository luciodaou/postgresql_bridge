# psql-cron

Scheduled exporter of PostgreSQL tables/views to JSON/CSV. One `.ini` file per sync in `syncs/`
(see `syncs/example.ini.template`). Runs as the `psql-cron` service of the root `docker-compose.yml`;
configuration and security settings are documented in the root README.
