-- psql entrypoint for a NEW tenant: creates base tables, then delivery control.
-- Existing tenant: apply only migrations/push/20261014_01_delivery_fencing.sql.
-- In a SQL editor run 00_base.sql, then the migration separately; \ir is psql-only.
\set ON_ERROR_STOP on
\ir 00_base.sql
\ir ../../migrations/push/20261014_01_delivery_fencing.sql
