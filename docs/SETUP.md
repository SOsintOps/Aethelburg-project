# Guida all'installazione — Aethelburg

## Requisiti di sistema

| Componente | Minimo | Consigliato |
|-----------|--------|-------------|
| OS | Windows 10 64-bit | Windows 11 |
| Python | 3.12 | 3.12.x (ultima patch) |
| RAM | 8GB | 16GB+ |
| Disco | 100GB liberi su SSD | 200GB su NVMe |
| Docker Desktop | WSL2 backend | WSL2 + 4GB RAM allocati |

---

## 1. Prerequisiti

### Python 3.12
Scarica da https://python.org/downloads — seleziona "Add to PATH" durante l'installazione.

```bash
python --version   # deve mostrare 3.12.x
```

### Docker Desktop
Scarica da https://docs.docker.com/desktop/install/windows-install/

- Abilita WSL2 integration durante l'installazione
- Dopo l'installazione: Settings → Resources → alloca almeno 4GB RAM a WSL2
- Verifica: `docker --version` e `docker compose version`

---

## 2. Installazione Aethelburg

```bash
# Clona il repository
git clone https://github.com/tuousername/aethelburg.git
cd aethelburg

# Crea e attiva l'ambiente virtuale
python -m venv .venv
.venv\Scripts\activate

# Installa dipendenze
pip install -r requirements.txt
```

---

## 3. Configurazione

```bash
# Copia il template delle variabili d'ambiente
copy .env.example .env
```

Modifica `.env` con un editor di testo. I campi obbligatori sono:
```
POSTGRES_PASSWORD=scegli_una_password_sicura
CH_API_KEY=la_tua_chiave_companies_house
```

La chiave API Companies House è gratuita: https://developer.company-information.service.gov.uk/

---

## 4. Avvio servizi Docker

```bash
# Avvia PostgreSQL, Nominatim
docker compose up -d

# Verifica che i servizi siano attivi
docker compose ps
```

Il primo avvio scarica le immagini Docker (~2GB). Nominatim scarica anche i dati OSM UK (~3GB) — può richiedere 30-60 minuti.

---

## 5. Inizializzazione database

```bash
# Applica le migration Alembic (crea lo schema)
python -m alembic upgrade head

# Installa le estensioni PostgreSQL
bash scripts/setup_db.sh
```

In caso di errori con `bash` su Windows, usa Git Bash o WSL2:
```bash
# Con Git Bash
"C:\Program Files\Git\bin\bash.exe" scripts/setup_db.sh
```

---

## 6. Caricamento dati

### Download dei dataset

| File | URL | Dimensione |
|------|-----|-----------|
| BasicCompanyDataAsOneFile | https://download.companieshouse.gov.uk/en_output.html | ~600MB ZIP |
| PSC Snapshot | https://download.companieshouse.gov.uk/persons-with-significant-control-snapshot-2016-04-06.zip | ~2GB ZIP |
| UK Sanctions OFSI | https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets | ~50MB |
| ICIJ Offshore Leaks | https://offshoreleaks.icij.org/pages/database | ~500MB ZIP |

Posiziona i file nella cartella `dati/`.

### Import (ordine obbligatorio)

```bash
# ~5 minuti
python scripts/import_sanctions.py

# ~1 ora
python scripts/import_icij.py

# ~1-2 ore
python scripts/import_companies.py

# ~2-3 ore (streaming, può essere interrotto e ripreso)
python scripts/import_psc.py
```

Ogni script mostra una progress bar e può essere interrotto con Ctrl+C. Alla ripresa, continua dal punto dove si era fermato (resume automatico via tabella staging).

---

## 7. Avvio applicazione

```bash
python src/main.py
```

Al primo avvio, il ServiceRegistry verifica la disponibilità di tutti i servizi e mostra lo stato nella status bar. Le funzionalità che richiedono servizi non disponibili vengono disabilitate automaticamente.

---

## Risoluzione problemi

**`docker compose up` fallisce con errore WSL2**
→ Riavvia Docker Desktop. Se persiste: Settings → Troubleshoot → Reset to factory defaults.

**Import PSC va in OOM (out of memory)**
→ Ridurre il chunk size: `python scripts/import_psc.py --chunk-size 5000`

**`bash scripts/setup_db.sh` non trovato**
→ Usa Git Bash: `"C:\Program Files\Git\bin\bash.exe" scripts/setup_db.sh`

**Mappa non si carica (tiles mancanti)**
→ Nominatim non è ancora pronto. Attendi il completamento del download OSM UK (~1h dal primo avvio Docker).

**PostgreSQL non raggiungibile**
→ Verifica che Docker stia girando e che il container `aethelburg-postgres` sia in stato `Up`:
```bash
docker compose ps
docker compose logs postgres
```

**Errore `age: function not found`**
→ Apache AGE non è stato installato correttamente. Riesegui:
```bash
bash scripts/setup_db.sh
```

---

## Disinstallazione

```bash
# Ferma e rimuovi i container Docker
docker compose down -v

# Rimuovi l'ambiente virtuale
rmdir /s .venv

# I dati in dati/ e il DB PostgreSQL rimangono su disco
# Per rimuovere anche il volume Docker:
docker volume rm aethelburg_postgres_data
```
