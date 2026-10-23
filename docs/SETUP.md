# Installation Guide — Aethelburg

## System requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 64-bit | Windows 11 |
| Python | 3.12 | 3.12.x (latest patch) |
| RAM | 8GB | 16GB+ |
| Disk | 100GB free on SSD | 200GB on NVMe |
| Docker Desktop | WSL2 backend | WSL2 + 4GB RAM allocated |

---

## 1. Prerequisites

### Python 3.12
Download from https://python.org/downloads — select "Add to PATH" during installation.

```bash
python --version   # should show 3.12.x
```

### Docker Desktop
Download from https://docs.docker.com/desktop/install/windows-install/

- Enable WSL2 integration during installation
- After installation: Settings → Resources → allocate at least 4GB RAM to WSL2
- Verify: `docker --version` and `docker compose version`

---

## 2. Installing Aethelburg

```bash
# Clone the repository
git clone https://github.com/SOsintOps/Aethelburg-project.git
cd Aethelburg-project

# Create the virtual environment and install (Windows, PowerShell)
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# The same on Linux
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

The README has the short version for each operating system and the launch commands (`start.ps1` on Windows, `start.sh` on Linux). Everything is installed inside `.venv` in the project folder; the data folder and the preferences file are the only other places written.

---

## 3. Configuration

```bash
# Copy the environment variables template
copy .env.example .env
```

Edit `.env` with a text editor. Required fields are:
```
POSTGRES_PASSWORD=choose_a_secure_password
CH_API_KEY=your_companies_house_api_key
```

The Companies House API key is free: https://developer.company-information.service.gov.uk/

---

## 4. Starting Docker services

```bash
# Start PostgreSQL, Nominatim
docker compose up -d

# Verify that services are running
docker compose ps
```

The first start downloads Docker images (~2GB). Nominatim also downloads UK OSM data (~3GB) — this may take 30–60 minutes.

---

## 5. Database initialisation

```bash
# Apply Alembic migrations (creates the schema)
python -m alembic upgrade head
```

---

## 6. Loading data

### Downloading the datasets

| File | URL | Size |
|------|-----|------|
| BasicCompanyDataAsOneFile | https://download.companieshouse.gov.uk/en_output.html | ~600MB ZIP |
| PSC Snapshot | https://download.companieshouse.gov.uk/en_pscdata.html | ~2GB ZIP |
| UK Sanctions OFSI | https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets | ~50MB |
| ICIJ Offshore Leaks | https://offshoreleaks.icij.org/pages/database | ~500MB ZIP |

Place the files in the `dati/` folder.

The OFSI Consolidated List closed on 28 January 2026 and is no longer updated: since then the FCDO [UK Sanctions List](https://www.gov.uk/government/publications/the-uk-sanctions-list) is the only UK source, and OpenSanctions (which includes it) is the primary sanctions source. An OFSI file is only an archive.

### Import (required order)

```bash
# ~5 minutes
python -m src.etl.import_sanctions

# ~1 hour
python -m src.etl.import_icij

# ~1-2 hours
python -m src.etl.import_companies

# ~2-3 hours (streaming, can be interrupted and resumed)
python -m src.etl.import_psc
```

Each script shows a progress bar and can be interrupted with Ctrl+C. On restart, it continues from where it stopped (automatic resume via staging table).

---

## 7. Starting the application

```bash
python -m src.main
```

On first launch, the ServiceRegistry checks the availability of all services and displays the status in the status bar. Features that require unavailable services are automatically disabled.

---

## Troubleshooting

**`docker compose up` fails with WSL2 error**
→ Restart Docker Desktop. If it persists: Settings → Troubleshoot → Reset to factory defaults.

**PSC import runs out of memory (OOM)**
→ Reduce the chunk size: `python scripts/import_psc.py --chunk-size 5000`

**Map does not load (missing tiles)**
→ Nominatim is not ready yet. Wait for the UK OSM download to complete (~1h from the first Docker start).

**PostgreSQL unreachable**
→ Verify that Docker is running and that the `aethelburg-postgres` container is in `Up` state:
```bash
docker compose ps
docker compose logs postgres
```

**Error `age: function not found`**
→ Apache AGE was not installed correctly. Re-run the Alembic migrations:
```bash
python -m alembic upgrade head
```

---

## Uninstallation

```bash
# Stop and remove Docker containers
docker compose down -v

# Remove the virtual environment
rmdir /s .venv

# Data in dati/ and the PostgreSQL DB remain on disk
# To also remove the Docker volume:
docker volume rm aethelburg_postgres_data
```
