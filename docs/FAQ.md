# FAQ — Aethelburg

## Installazione e setup

**Q: Docker è obbligatorio?**
Il database PostgreSQL (con PostGIS, pgvector e Apache AGE) gira in Docker. È il modo più affidabile su Windows per avere tutte le estensioni compilate correttamente. Senza Docker il sistema non si avvia.

**Q: Quanto spazio disco serve?**
- Database PostgreSQL completo (tutte le fonti): ~80–120GB
- Dataset grezzi (dati/): ~15GB
- Modello ML sentence-transformers: ~80MB
- Tiles mappa MBTiles UK: ~2–5GB (opzionale, per uso offline)
- Totale consigliato: almeno 200GB liberi su SSD

**Q: Funziona su SSD esterno o HDD?**
L'import iniziale dei dati (specialmente il PSC da 12GB) è molto più lento su HDD — stimare 6-12 ore invece di 2-4. Per uso normale dopo l'import, un HDD è accettabile.

**Q: Quanto RAM serve?**
16GB sono il minimo consigliato. Con 8GB si può usare il sistema ma l'import PSC richiede chunk size ridotti e alcune analisi di rete potrebbero fallire su subgraph grandi.

---

## Dati

**Q: Come aggiorno i dati Companies House?**
Companies House pubblica un nuovo bulk snapshot mensile. APScheduler gestisce il download automatico e il caricamento differenziale. Puoi anche triggherare manualmente da `Impostazioni → Aggiornamento dati`.

**Q: Come aggiorno le sanzioni?**
OpenSanctions pubblica aggiornamenti giornalieri. Il sistema scarica automaticamente il dataset ogni notte (se l'applicazione è aperta) o al prossimo avvio.

**Q: Il file UK Sanctions OFSI è aggiornato?**
No — l'OFSI ha smesso di aggiornare la Consolidated List il 28 gennaio 2026. Aethelburg usa OpenSanctions come fonte primaria, che include UK FCDO Sanctions, OFAC e altre 327 fonti globali.

**Q: I dati ICIJ Offshore Leaks vengono aggiornati automaticamente?**
No. ICIJ pubblica aggiornamenti periodici ma non giornalieri. Controlla https://offshoreleaks.icij.org/ per nuove release e riesegui `scripts/import_icij.py` manualmente.

**Q: Perché molte aziende non hanno coordinate sulla mappa?**
Il geocoding completo di 5.67M indirizzi richiederebbe settimane con Nominatim locale. Aethelburg usa due approcci: (1) centroidi di PostCode dal dataset ONSPD (copertura immediata ~90%) e (2) geocoding preciso via Nominatim on-demand quando l'utente apre una scheda aziendale.

**Q: Perché non ci sono i direttori (officers) per tutte le aziende?**
Companies House non distribuisce i dati officers in bulk. Sono disponibili solo tramite API (`/company/{id}/officers`), limitata a 600 chiamate ogni 5 minuti. Il sistema fetcha automaticamente gli officers per le aziende con risk score più alto.

---

## Analisi e intelligence

**Q: Cosa significa il risk score 0–100?**
È un punteggio composito calcolato da fino a 8 pattern di detection. Un punteggio alto non indica certezza di illecito — indica anomalie statistiche che meritano approfondimento. Ogni flag è etichettato con un ID tecnica FT3 per documentare la motivazione.

**Q: Quanti falsi positivi ci sono?**
Dipende dal pattern. Il pattern "indirizzo condiviso" da solo produce molti falsi positivi (agenti di incorporazione legittimi). Il sistema usa score composito: più pattern si sovrappongono, più affidabile è il segnale. Non usare mai un singolo flag come evidenza definitiva.

**Q: Come funziona il matching con le sanzioni se non c'è il company number?**
Il campo `business_registration_number` nel file OFSI è sempre vuoto. Il matching avviene per nome (normalizzazione + Levenshtein/Jaro-Winkler). Il risultato è espresso come confidence score, non come match definitivo. Confidence < 0.7 viene mostrato come "possibile match".

**Q: Il sistema può identificare ownership circolari?**
Sì, tramite Apache AGE (graph database integrato in PostgreSQL). Query Cypher cercano pattern `(A)-[:CONTROLS*1..5]->(A)` (cicli). Funziona però solo quando i dati degli officers sono disponibili per formare la catena completa.

---

## Privacy e legalità

**Q: È legale usare questi dati?**
Sì per uso personale. I dati Companies House sono Open Government Licence v3. I dati PSC sono pubblici per legge (Companies Act 2006). OpenSanctions e ICIJ sono CC-BY-NC (non commerciale). Vedere [LEGAL.md](LEGAL.md) per l'analisi completa.

**Q: Si applica il GDPR / UK GDPR?**
I dati PSC contengono dati personali (nome, DOB parziale, nazionalità). L'esenzione domestica (Art. 2(2)(c) UK GDPR) copre il trattamento per uso strettamente personale. Non condividere né pubblicare output del sistema che contengano dati personali di individui. Le query API con nomi di persone fisiche verso servizi esterni escono dall'esenzione domestica.

**Q: Posso usare Aethelburg per scopi professionali o commerciali?**
No nella configurazione attuale. Le licenze CC-BY-NC di OpenSanctions e ICIJ vietano l'uso commerciale. Per uso professionale, contattare direttamente OpenSanctions per una licenza commerciale.

---

## Tecnico

**Q: Perché PySide6 e non PyQt5?**
PySide6 è la versione ufficiale del Qt Company, con licenza LGPL (non GPL). API identica a PyQt5. Per un'applicazione desktop distribuibile, LGPL è molto più flessibile di GPL.

**Q: Perché PostgreSQL e non SQLite?**
Per le estensioni: PostGIS (geospatial), pgvector (vector search), Apache AGE (graph database). Nessuna di queste esiste per SQLite. Con 20M+ record e query analitiche complesse, PostgreSQL è l'unica scelta praticabile.

**Q: RuVector è incluso?**
RuVector (Docker microservice per vector search con GNN self-learning) è incluso nel docker-compose ma commentato per default. Si attiva manualmente quando il volume di vettori supera ~10M e si vuole abilitare il layer GNN. pgvector con binary quantization gestisce i casi d'uso iniziali.

**Q: Posso eseguire Aethelburg senza Docker?**
No. PostgreSQL con le estensioni richieste (PostGIS, pgvector, Apache AGE) non può essere installato facilmente su Windows senza Docker. In futuro si potrebbe valutare PostgreSQL portable pre-configurato.
