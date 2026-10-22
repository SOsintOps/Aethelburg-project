#!/usr/bin/env bash
# setup_db.sh: first-time setup of the optional PostgreSQL backend
# Starts Docker, waits for PostgreSQL, runs the Alembic migrations
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# Prerequisites
command -v docker >/dev/null 2>&1 || error "Docker not found: install Docker Desktop."
command -v python >/dev/null 2>&1 || error "Python not found."

# .env
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log ".env not found: copying .env.example..."
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    error "Set the passwords in ${PROJECT_ROOT}/.env, then run this script again."
fi

# Load the variables
set -a; source "${PROJECT_ROOT}/.env"; set +a

# Start Docker
log "Starting the Docker container..."
cd "${PROJECT_ROOT}"
docker compose up -d db

# Wait for PostgreSQL
log "Waiting for PostgreSQL (up to 60 s)..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until docker compose exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
        error "PostgreSQL did not answer after ${MAX_ATTEMPTS} attempts."
    fi
    sleep 2
done
log "PostgreSQL is ready."

# Extensions
log "Checking the PostgreSQL extensions..."
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "\dx" | grep -E "postgis|vector|age" || \
    log "WARNING: some extensions may be missing."

# Alembic migrations
log "Running the Alembic migrations..."
cd "${PROJECT_ROOT}"
python -m alembic upgrade head

log ""
log "Setup complete."
log "  DB: postgresql://${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
log ""
log "Next steps:"
log "  python -m src.main data download   (Companies House, PSC, sanctions, ONSPD)"
log "  python -m src.main data import     (subset import, sanctions, ONSPD, scoring)"
