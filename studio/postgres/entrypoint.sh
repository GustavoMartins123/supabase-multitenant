#!/bin/bash
set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting PostgreSQL initialization..."

until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    log "Waiting for PostgreSQL to be ready..."
    sleep 2
done

log "PostgreSQL is ready!"

if ! psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt users' | grep -q 'users'; then
    log "First run detected. Initializing database schema..."
    
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/init.sql
    
    log "Database schema initialized successfully!"
else
    log "Database already initialized. Skipping schema creation."
fi

log "PostgreSQL initialization completed!"