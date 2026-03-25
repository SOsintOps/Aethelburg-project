# Note legali — Aethelburg

## Fonti dati: analisi delle licenze

### Companies House
- **Licenza**: Open Government Licence v3.0 (OGL)
- **URL**: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/
- **Uso commerciale**: Consentito con attribuzione
- **Redistribuzione**: Consentita con attribuzione
- **Note**: Aethelburg non ridistribuisce i dati. Uso locale conforme a OGL.

### PSC (Persons with Significant Control)
- **Fonte**: Companies House (stesso regime OGL)
- **Contenuto**: Dati personali di persone fisiche (nome, DOB parziale, nazionalità)
- **Regime**: UK GDPR / Data Protection Act 2018
- **Esenzione applicabile**: Art. 2(2)(c) UK GDPR — attività a carattere esclusivamente personale o domestico
- **Limite**: L'esenzione domestica NON copre la comunicazione a terzi né le query API con dati personali verso server esterni.

### ICIJ Offshore Leaks Database
- **Licenza**: Creative Commons Attribution-NonCommercial (CC-BY-NC)
- **URL**: https://offshoreleaks.icij.org/pages/legal
- **Uso commerciale**: Vietato
- **Redistribuzione**: Consentita con attribuzione e per uso non commerciale
- **Note**: ICIJ richiede attribuzione nelle pubblicazioni che utilizzano i dati.

### OpenSanctions
- **Licenza**: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC-BY-NC-SA)
- **URL**: https://www.opensanctions.org/licensing/
- **Uso commerciale**: Vietato
- **Redistribuzione**: Consentita con attribuzione, stessa licenza (share-alike)
- **Conflitto**: In caso di distribuzione di dataset combinati OGL + CC-BY-NC-SA, il dataset derivato deve essere CC-BY-NC-SA. Per uso personale non distribuito: nessun conflitto.
- **Licenza commerciale**: Disponibile su richiesta a OpenSanctions.

### FollowTheMoney (FtM)
- **Licenza**: MIT
- **Autore**: OCCRP (Organized Crime and Corruption Reporting Project)
- **Uso commerciale**: Consentito
- **Note**: Libreria Python, non dataset.

### FT3 Framework (Stripe)
- **Licenza**: MIT
- **URL**: https://github.com/stripe/ft3
- **Note**: Knowledge base JSON/CSV, non libreria eseguibile. MIT permette uso libero.

### sentence-transformers / all-MiniLM-L6-v2
- **Licenza**: Apache 2.0
- **Uso commerciale**: Consentito

---

## UK GDPR: analisi dell'esenzione domestica

Il trattamento dei dati PSC rientra nell'esenzione domestica (Art. 2(2)(c) UK GDPR) a condizione che:

1. Il trattamento avvenga su macchina locale (non cloud)
2. I risultati non vengano condivisi con terzi
3. I dati non vengano usati per prendere decisioni che impattano direttamente individui
4. Le query API verso servizi esterni non contengano dati di persone fisiche identificabili

**Zone grigie**:
- Query API verso Companies House, OpenCorporates o altri servizi con parametri di ricerca contenenti nomi di persone fisiche = trasferimento di dati fuori dal perimetro domestico. Non coperto dall'esenzione.
- Output aggregati (es. "top 10 direttori più comuni nelle aziende sanzionate") = probabilmente coperto dall'esenzione se rimane personale.

**Raccomandazione**: Usare preferibilmente dataset locali (bulk download) per ricerche su persone fisiche, evitando query nominative verso API esterne.

---

## Nota sull'uso investigativo

Aethelburg produce indicazioni di rischio statistico, non evidenze legali. Un risk score elevato indica anomalie meritevoli di approfondimento, non certezza di illecito. L'utente è responsabile della verifica delle informazioni prima di trarre conclusioni o intraprendere azioni.

Il sistema non è progettato né autorizzato per:
- Prendere decisioni automatiche che impattano diritti di persone fisiche
- Essere usato come strumento di sorveglianza
- Produrre evidenze per procedimenti legali senza verifica indipendente
