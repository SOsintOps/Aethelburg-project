#!/usr/bin/env bash
# setup_db.sh — Setup iniziale database Aethelburg
# Avvia Docker, attende che PostgreSQL sia pronto, esegue le migrazioni Alembic
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# Verifica prerequisiti
command -v docker >/dev/null 2>&1 || error "Docker non trovato. Installare Docker Desktop."
command -v python >/dev/null 2>&1 || error "Python non trovato."

# Verifica .env
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log "File .env non trovato. Copiando .env.example..."
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    error "Modifica ${PROJECT_ROOT}/.env con le password corrette, poi esegui di nuovo."
fi

# Carica variabili
set -a; source "${PROJECT_ROOT}/.env"; set +a

# Avvia Docker
log "Avvio container Docker..."
cd "${PROJECT_ROOT}"
docker compose up -d db

# Attendi PostgreSQL ready
log "Attesa PostgreSQL (max 60s)..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until docker compose exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
        error "PostgreSQL non risponde dopo ${MAX_ATTEMPTS} tentativi."
    fi
    sleep 2
done
log "PostgreSQL pronto."

# Verifica estensioni
log "Verifica estensioni PostgreSQL..."
docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "\dx" | grep -E "postgis|vector|age" || \
    log "ATTENZIONE: alcune estensioni potrebbero non essere installate."

# Esegui migrazioni Alembic
log "Esecuzione migrazioni Alembic..."
cd "${PROJECT_ROOT}"
python -m alembic upgrade head

log ""
log "Setup completato."
log "  DB: postgresql://${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
log ""
log "Prossimi passi:"
log "  1. Scarica ONSPD da https://geoportal.statistics.gov.uk/"
log "  2. Scarica bulk data Companies House da https://download.companieshouse.gov.uk/"
log "  3. python -m src.etl.import_sanctions  (UK Sanctions — 5min)"
log "  4. python -m src.etl.import_icij       (ICIJ — 1h)"
log "  5. python -m src.etl.import_companies  (Companies House — 1-2h)"
log "  6. python -m src.etl.import_psc        (PSC — 2-3h)"
