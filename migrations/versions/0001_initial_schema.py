"""Schema iniziale Aethelburg — ontologia v1.0.0

Revision ID: 0001
Revises:
Create Date: 2026-03-26

Crea:
  - Schema public: tabelle dati sorgente (Companies House, PSC, ICIJ, Sanctions, PEP, Geo)
  - Schema casework: tabelle investigative
  - Estensioni: postgis, vector, age, pg_trgm, unaccent, uuid-ossp
  - Indici critici per performance
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # ESTENSIONI                                                           #
    # ------------------------------------------------------------------ #
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS age")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Schema casework separato (ADR-012)
    op.execute("CREATE SCHEMA IF NOT EXISTS casework")

    # ------------------------------------------------------------------ #
    # TABELLA: data_sources — provenance di ogni dato (Layer 5 ontologia) #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE data_sources (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_name     VARCHAR(100) NOT NULL,
        source_type     VARCHAR(50)  NOT NULL,
        source_version  VARCHAR(50),
        source_url      TEXT,
        collected_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
        file_hash       VARCHAR(64),
        record_count    BIGINT,
        notes           TEXT,
        CONSTRAINT uq_source_version UNIQUE (source_name, source_version)
    )
    """)

    # ------------------------------------------------------------------ #
    # TABELLA: geo_postcode_centroids — ONSPD (ADR-011)                   #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE geo_postcode_centroids (
        postcode        VARCHAR(10)  PRIMARY KEY,
        lat             DOUBLE PRECISION NOT NULL,
        lon             DOUBLE PRECISION NOT NULL,
        geom            GEOMETRY(POINT, 4326) GENERATED ALWAYS AS
                            (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED,
        admin_district  VARCHAR(100),
        admin_county    VARCHAR(100),
        admin_ward      VARCHAR(100),
        nuts_level1     VARCHAR(10),
        country_code    CHAR(1),
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_geo_postcode_geom ON geo_postcode_centroids USING gist(geom)")

    # ------------------------------------------------------------------ #
    # TABELLA: companies — Companies House bulk data                       #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE companies (
        -- Identificatore
        company_number          VARCHAR(8)   PRIMARY KEY,
        company_name            VARCHAR(500) NOT NULL,

        -- Indirizzo registrato
        reg_address_care_of     VARCHAR(200),
        reg_address_po_box      VARCHAR(50),
        reg_address_line1       VARCHAR(300),
        reg_address_line2       VARCHAR(300),
        reg_address_post_town   VARCHAR(100),
        reg_address_county      VARCHAR(100),
        reg_address_country     VARCHAR(100),
        reg_address_postcode    VARCHAR(10),

        -- Tipo e stato
        company_category        VARCHAR(100),
        company_status          VARCHAR(50),
        country_of_origin       VARCHAR(100),

        -- Date
        dissolution_date        DATE,
        incorporation_date      DATE,

        -- Conti
        accounts_account_ref_day    SMALLINT,
        accounts_account_ref_month  SMALLINT,
        accounts_account_category   VARCHAR(50),
        accounts_account_date       DATE,
        accounts_next_due_date      DATE,
        accounts_last_made_up_date  DATE,

        -- Returns
        returns_next_due_date       DATE,
        returns_last_made_up_date   DATE,

        -- Ipoteche
        mortgages_num_charges           SMALLINT DEFAULT 0,
        mortgages_num_outstanding       SMALLINT DEFAULT 0,
        mortgages_num_part_satisfied    SMALLINT DEFAULT 0,
        mortgages_num_satisfied         SMALLINT DEFAULT 0,

        -- Codici SIC (testo CH: "74100 - descrizione")
        sic_text_1  VARCHAR(200),
        sic_text_2  VARCHAR(200),
        sic_text_3  VARCHAR(200),
        sic_text_4  VARCHAR(200),

        -- Codici SIC (solo numero, estratto da sic_text)
        sic_code_1  VARCHAR(10),
        sic_code_2  VARCHAR(10),
        sic_code_3  VARCHAR(10),
        sic_code_4  VARCHAR(10),

        -- Limited partnerships
        lp_num_gen_partners SMALLINT,
        lp_num_lim_partners SMALLINT,

        -- URI
        ch_uri          VARCHAR(200),

        -- Nomi precedenti (fino a 10)
        prev_name_1_date    DATE,
        prev_name_1         VARCHAR(500),
        prev_name_2_date    DATE,
        prev_name_2         VARCHAR(500),
        prev_name_3_date    DATE,
        prev_name_3         VARCHAR(500),
        prev_name_4_date    DATE,
        prev_name_4         VARCHAR(500),
        prev_name_5_date    DATE,
        prev_name_5         VARCHAR(500),
        prev_name_6_date    DATE,
        prev_name_6         VARCHAR(500),
        prev_name_7_date    DATE,
        prev_name_7         VARCHAR(500),
        prev_name_8_date    DATE,
        prev_name_8         VARCHAR(500),
        prev_name_9_date    DATE,
        prev_name_9         VARCHAR(500),
        prev_name_10_date   DATE,
        prev_name_10        VARCHAR(500),

        -- Confirmation statement
        conf_stmt_next_due_date     DATE,
        conf_stmt_last_made_up_date DATE,

        -- Aethelburg computed fields
        address_fingerprint     VARCHAR(200),   -- postcode|house_no|keyword (ADR-015)
        name_fingerprint        VARCHAR(500),   -- fingerprints.generate(company_name)
        risk_score              FLOAT DEFAULT 0.0,
        ft3_techniques          VARCHAR(20)[],
        officers_fetched_at     TIMESTAMPTZ,    -- ultimo fetch officers via API
        is_flagged              BOOLEAN DEFAULT false,

        -- Provenance
        source_id       UUID REFERENCES data_sources(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    # Indici companies
    op.execute("CREATE INDEX idx_companies_name ON companies USING gin(to_tsvector('simple', company_name))")
    op.execute("CREATE INDEX idx_companies_fingerprint ON companies(name_fingerprint)")
    op.execute("CREATE INDEX idx_companies_postcode ON companies(reg_address_postcode)")
    op.execute("CREATE INDEX idx_companies_addr_fp ON companies(address_fingerprint)")
    op.execute("CREATE INDEX idx_companies_status ON companies(company_status)")
    op.execute("CREATE INDEX idx_companies_risk ON companies(risk_score DESC) WHERE is_flagged = true")
    op.execute("CREATE INDEX idx_companies_sic1 ON companies(sic_code_1)")
    op.execute("CREATE INDEX idx_companies_incorporation ON companies(incorporation_date)")

    # ------------------------------------------------------------------ #
    # TABELLA: persons — persone fisiche (PSC individuali, directors, PEP) #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE persons (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                    VARCHAR(500) NOT NULL,
        name_fingerprint        VARCHAR(500),
        forename                VARCHAR(200),
        surname                 VARCHAR(200),
        title                   VARCHAR(50),
        nationality             VARCHAR(100),
        country_of_residence    VARCHAR(100),
        dob_month               SMALLINT,
        dob_year                SMALLINT,
        is_pep                  BOOLEAN DEFAULT false,
        pep_source              VARCHAR(50),    -- 'opensanctions' | 'everypolitician'
        source_id               UUID REFERENCES data_sources(id),
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_persons_fingerprint ON persons(name_fingerprint)")
    op.execute("CREATE INDEX idx_persons_name_fts ON persons USING gin(to_tsvector('simple', name))")
    op.execute("CREATE INDEX idx_persons_pep ON persons(is_pep) WHERE is_pep = true")

    # ------------------------------------------------------------------ #
    # TABELLA: legal_entities — PSC corporate, entità straniere           #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE legal_entities (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                    VARCHAR(500) NOT NULL,
        name_fingerprint        VARCHAR(500),
        jurisdiction            VARCHAR(10),    -- ISO 3166-1 alpha-2
        company_number_foreign  VARCHAR(100),
        entity_type             VARCHAR(50),    -- 'corporate-psc' | 'legal-person' | 'trust' | ...
        is_offshore             BOOLEAN DEFAULT false,
        source_id               UUID REFERENCES data_sources(id),
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_legal_entities_fingerprint ON legal_entities(name_fingerprint)")
    op.execute("CREATE INDEX idx_legal_entities_jurisdiction ON legal_entities(jurisdiction)")

    # ------------------------------------------------------------------ #
    # TABELLA: psc_ownerships — PSC ownership stakes (FtM: Ownership)     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE psc_ownerships (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_number      VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        -- Chi controlla: persona fisica O legal entity (uno dei due è NOT NULL)
        person_id           UUID REFERENCES persons(id),
        legal_entity_id     UUID REFERENCES legal_entities(id),
        -- Tipo controllo
        nature_of_control   VARCHAR(100)[],  -- array di stringhe CH
        notified_on         DATE,
        ceased_on           DATE,
        is_ceased           BOOLEAN DEFAULT false,
        is_super_secure     BOOLEAN DEFAULT false,  -- dati oscurati CH
        source_id           UUID REFERENCES data_sources(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_psc_owner CHECK (
            (person_id IS NOT NULL AND legal_entity_id IS NULL) OR
            (person_id IS NULL AND legal_entity_id IS NOT NULL)
        )
    )
    """)
    op.execute("CREATE INDEX idx_psc_company ON psc_ownerships(company_number)")
    op.execute("CREATE INDEX idx_psc_person ON psc_ownerships(person_id) WHERE person_id IS NOT NULL")
    op.execute("CREATE INDEX idx_psc_legal ON psc_ownerships(legal_entity_id) WHERE legal_entity_id IS NOT NULL")
    op.execute("CREATE INDEX idx_psc_active ON psc_ownerships(company_number) WHERE is_ceased = false")

    # ------------------------------------------------------------------ #
    # TABELLA: directorships — incarichi direttoriali (FtM: Directorship)  #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE directorships (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_number      VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        person_id           UUID REFERENCES persons(id),
        officer_role        VARCHAR(100),   -- director | secretary | llp-member | ...
        appointed_on        DATE,
        resigned_on         DATE,
        is_active           BOOLEAN DEFAULT true,
        occupation          VARCHAR(200),
        nationality         VARCHAR(100),
        country_of_residence VARCHAR(100),
        -- Dati fetched on-demand via CH API
        api_person_id       VARCHAR(100),   -- CH officer ID (per link API)
        source_id           UUID REFERENCES data_sources(id),
        fetched_via         VARCHAR(20),    -- 'bulk' | 'api' | 'streaming'
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_dir_company ON directorships(company_number)")
    op.execute("CREATE INDEX idx_dir_person ON directorships(person_id) WHERE person_id IS NOT NULL")
    op.execute("CREATE INDEX idx_dir_active ON directorships(company_number) WHERE is_active = true")

    # ------------------------------------------------------------------ #
    # TABELLA: officers_fetch_queue — coda on-demand fetch directors       #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE officers_fetch_queue (
        id              BIGSERIAL PRIMARY KEY,
        company_number  VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        priority        SMALLINT DEFAULT 5,     -- 1=altissima (flagged), 5=normale
        status          VARCHAR(20) DEFAULT 'pending',  -- pending | in_progress | done | error
        enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at      TIMESTAMPTZ,
        completed_at    TIMESTAMPTZ,
        error_msg       TEXT,
        UNIQUE (company_number, status)
    )
    """)
    op.execute("CREATE INDEX idx_queue_priority ON officers_fetch_queue(priority, enqueued_at) WHERE status = 'pending'")

    # ------------------------------------------------------------------ #
    # TABELLA: streaming_checkpoints — posizione streaming CH API          #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE streaming_checkpoints (
        stream_type     VARCHAR(50) PRIMARY KEY,  -- 'officers' | 'psc' | 'company_profile'
        last_event_id   VARCHAR(100),
        last_seq_num    BIGINT,
        last_event_at   TIMESTAMPTZ,
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("""
    INSERT INTO streaming_checkpoints (stream_type) VALUES
        ('officers'), ('psc'), ('company_profile')
    """)

    # ------------------------------------------------------------------ #
    # TABELLA: sanctions — entità sanzionate (OpenSanctions/OFSI)          #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE sanctions (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name            VARCHAR(500) NOT NULL,
        name_fingerprint VARCHAR(500),
        aliases         TEXT[],
        entity_type     VARCHAR(50),        -- 'Person' | 'Company' | 'Organization'
        topics          VARCHAR(50)[],      -- 'sanction' | 'pep' | 'debarment' | ...
        countries       VARCHAR(10)[],
        list_name       VARCHAR(100),       -- 'UK FCDO' | 'OFAC' | 'EU' | ...
        listed_on       DATE,
        source          VARCHAR(50),        -- 'opensanctions' | 'ofsi'
        opensanctions_id VARCHAR(100),      -- ID stabile OpenSanctions
        raw_properties  JSONB,              -- tutte le proprietà FtM originali
        source_id       UUID REFERENCES data_sources(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_sanctions_fingerprint ON sanctions(name_fingerprint)")
    op.execute("CREATE INDEX idx_sanctions_topics ON sanctions USING gin(topics)")
    op.execute("CREATE INDEX idx_sanctions_name_fts ON sanctions USING gin(to_tsvector('simple', name))")

    # ------------------------------------------------------------------ #
    # TABELLA: pep_persons — Politically Exposed Persons                   #
    # (ADR-018: OpenSanctions + EveryPolitician)                           #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE pep_persons (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name            VARCHAR(500) NOT NULL,
        name_fingerprint VARCHAR(500),
        country         VARCHAR(10),        -- ISO 3166-1 alpha-2
        party           VARCHAR(200),
        legislature     VARCHAR(200),
        mandate_start   DATE,
        mandate_end     DATE,
        is_current      BOOLEAN DEFAULT false,
        pep_source      VARCHAR(50) NOT NULL,  -- 'opensanctions' | 'everypolitician'
        external_id     VARCHAR(200),          -- ID nella fonte originale
        source_id       UUID REFERENCES data_sources(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_pep_fingerprint ON pep_persons(name_fingerprint)")
    op.execute("CREATE INDEX idx_pep_country ON pep_persons(country)")

    # ------------------------------------------------------------------ #
    # TABELLA: name_variants — normalizzazione multi-script (ADR-017)      #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE name_variants (
        id              BIGSERIAL PRIMARY KEY,
        entity_id       UUID NOT NULL,
        entity_type     VARCHAR(30) NOT NULL,   -- 'company' | 'person' | 'legal_entity' | 'sanction' | 'pep'
        variant_text    VARCHAR(500) NOT NULL,
        fingerprint     VARCHAR(500),           -- fingerprints.generate(variant_text)
        ftm_id          VARCHAR(64),            -- make_id() hash per dedup cross-source
        variant_type    VARCHAR(30),            -- 'original' | 'alias' | 'phonetic_key' | 'transliterated'
        source_id       UUID REFERENCES data_sources(id),
        UNIQUE (entity_id, entity_type, fingerprint)
    )
    """)
    op.execute("CREATE INDEX idx_name_variants_fingerprint ON name_variants(fingerprint)")
    op.execute("CREATE INDEX idx_name_variants_entity ON name_variants(entity_id, entity_type)")
    op.execute("CREATE INDEX idx_name_variants_fts ON name_variants USING gin(to_tsvector('simple', variant_text))")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_entities — ICIJ Offshore Leaks entities               #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_entities (
        node_id         VARCHAR(50) PRIMARY KEY,    -- ICIJ node_id (non stabile cross-release)
        name            VARCHAR(500),
        name_fingerprint VARCHAR(500),
        original_name   VARCHAR(500),
        former_name     VARCHAR(500),
        jurisdiction    VARCHAR(200),
        jurisdiction_description VARCHAR(200),
        company_type    VARCHAR(200),
        address         TEXT,
        internal_id     VARCHAR(100),
        incorporation_date DATE,
        inactivation_date  DATE,
        struck_off_date    DATE,
        status          VARCHAR(100),
        source_id_list  VARCHAR(200),               -- 'Panama Papers' | 'Pandora Papers' | ...
        valid_until     VARCHAR(100),               -- ICIJ release version
        note            TEXT,
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_entities_fp ON icij_entities(name_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_officers — ICIJ officers/intermediaries               #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_officers (
        node_id         VARCHAR(50) PRIMARY KEY,
        name            VARCHAR(500),
        name_fingerprint VARCHAR(500),
        icij_id         VARCHAR(100),
        valid_until     VARCHAR(100),
        country_codes   VARCHAR(200),
        countries       VARCHAR(500),
        source_id_list  VARCHAR(200),
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_officers_fp ON icij_officers(name_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_relationships — ICIJ relationship edges               #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_relationships (
        id              BIGSERIAL PRIMARY KEY,
        node_id_start   VARCHAR(50) NOT NULL,
        node_id_end     VARCHAR(50) NOT NULL,
        rel_type        VARCHAR(100),
        link            VARCHAR(200),
        start_date      DATE,
        end_date        DATE,
        source_id_list  VARCHAR(200),
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_rel_start ON icij_relationships(node_id_start)")
    op.execute("CREATE INDEX idx_icij_rel_end ON icij_relationships(node_id_end)")

    # ------------------------------------------------------------------ #
    # TABELLA: risk_flags — pattern FT3 rilevati (ADR-016)                #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE risk_flags (
        id                  BIGSERIAL PRIMARY KEY,
        company_number      VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        ft3_technique       VARCHAR(20) NOT NULL,   -- 'FT3-SC-001' ecc.
        priority            VARCHAR(10) NOT NULL,   -- 'CRITICAL' | 'HIGH' | 'MEDIUM'
        score_contribution  FLOAT NOT NULL DEFAULT 0.0,
        evidence            JSONB NOT NULL DEFAULT '{}',
        source_ids          UUID[],                 -- provenance multi-sorgente
        detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
        is_active           BOOLEAN NOT NULL DEFAULT true,
        UNIQUE (company_number, ft3_technique)      -- un flag per tecnica per azienda
    )
    """)
    op.execute("CREATE INDEX idx_risk_company ON risk_flags(company_number) WHERE is_active = true")
    op.execute("CREATE INDEX idx_risk_technique ON risk_flags(ft3_technique)")
    op.execute("CREATE INDEX idx_risk_critical ON risk_flags(company_number) WHERE priority = 'CRITICAL' AND is_active = true")

    # ------------------------------------------------------------------ #
    # TABELLA: entity_events — change detection log                        #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE entity_events (
        id              BIGSERIAL PRIMARY KEY,
        event_type      VARCHAR(50) NOT NULL,   -- 'company_dissolved' | 'director_resigned' | 'psc_changed' | ...
        entity_type     VARCHAR(30) NOT NULL,   -- 'company' | 'person' | 'directorship' | 'psc'
        entity_id       VARCHAR(100) NOT NULL,  -- company_number o UUID
        old_value       JSONB,
        new_value       JSONB,
        detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        source          VARCHAR(50)             -- 'bulk_compare' | 'streaming' | 'api'
    )
    """)
    op.execute("CREATE INDEX idx_events_entity ON entity_events(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_events_type ON entity_events(event_type)")
    op.execute("CREATE INDEX idx_events_date ON entity_events(detected_at DESC)")

    # ------------------------------------------------------------------ #
    # SCHEMA CASEWORK — investigazioni (ADR-012)                           #
    # ------------------------------------------------------------------ #

    op.execute("""
    CREATE TABLE casework.investigations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title           VARCHAR(500) NOT NULL,
        description     TEXT,
        status          VARCHAR(30) NOT NULL DEFAULT 'open',
        -- open | in_progress | pending_review | closed | archived
        priority        VARCHAR(10) DEFAULT 'medium',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        closed_at       TIMESTAMPTZ
    )
    """)

    op.execute("""
    CREATE TABLE casework.investigation_entities (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
        entity_type         VARCHAR(30) NOT NULL,   -- 'company' | 'person' | 'legal_entity'
        entity_id           VARCHAR(100) NOT NULL,  -- company_number o UUID
        added_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
        notes               TEXT,
        UNIQUE (investigation_id, entity_type, entity_id)
    )
    """)
    op.execute("CREATE INDEX idx_inv_entities_inv ON casework.investigation_entities(investigation_id)")

    op.execute("""
    CREATE TABLE casework.annotations (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
        entity_type         VARCHAR(30),
        entity_id           VARCHAR(100),
        annotation_text     TEXT NOT NULL,
        annotation_type     VARCHAR(30) DEFAULT 'note',  -- note | flag | finding | todo
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.manual_links (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID REFERENCES casework.investigations(id) ON DELETE SET NULL,
        from_entity_type    VARCHAR(30) NOT NULL,
        from_entity_id      VARCHAR(100) NOT NULL,
        to_entity_type      VARCHAR(30) NOT NULL,
        to_entity_id        VARCHAR(100) NOT NULL,
        link_type           VARCHAR(100),
        confidence          FLOAT DEFAULT 1.0,
        evidence            TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.visual_snapshots (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
        title               VARCHAR(300),
        snapshot_png_b64    TEXT,           -- PNG base64 inline
        graph_json          JSONB,          -- stato cytoscape serializzato
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.saved_queries (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID REFERENCES casework.investigations(id) ON DELETE SET NULL,
        title               VARCHAR(300) NOT NULL,
        query_type          VARCHAR(30) NOT NULL,  -- 'sql' | 'cypher' | 'fts'
        query_text          TEXT NOT NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.investigation_events (
        id                  BIGSERIAL PRIMARY KEY,
        investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
        event_type          VARCHAR(50) NOT NULL,
        description         TEXT,
        metadata            JSONB DEFAULT '{}',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_inv_events_inv ON casework.investigation_events(investigation_id)")

    op.execute("""
    CREATE TABLE casework.generated_reports (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID REFERENCES casework.investigations(id) ON DELETE SET NULL,
        title               VARCHAR(500) NOT NULL,
        format              VARCHAR(20) NOT NULL,   -- 'pdf' | 'ftm_json' | 'xlsx' | 'gexf' | 'geojson' | 'kml'
        file_path           TEXT,                   -- percorso locale del file generato
        file_size_bytes     BIGINT,
        generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        generation_params   JSONB DEFAULT '{}'
    )
    """)


def downgrade() -> None:
    # Casework
    op.execute("DROP TABLE IF EXISTS casework.generated_reports")
    op.execute("DROP TABLE IF EXISTS casework.investigation_events")
    op.execute("DROP TABLE IF EXISTS casework.saved_queries")
    op.execute("DROP TABLE IF EXISTS casework.visual_snapshots")
    op.execute("DROP TABLE IF EXISTS casework.manual_links")
    op.execute("DROP TABLE IF EXISTS casework.annotations")
    op.execute("DROP TABLE IF EXISTS casework.investigation_entities")
    op.execute("DROP TABLE IF EXISTS casework.investigations")
    op.execute("DROP SCHEMA IF EXISTS casework")

    # Public
    op.execute("DROP TABLE IF EXISTS risk_flags")
    op.execute("DROP TABLE IF EXISTS entity_events")
    op.execute("DROP TABLE IF EXISTS name_variants")
    op.execute("DROP TABLE IF EXISTS icij_relationships")
    op.execute("DROP TABLE IF EXISTS icij_officers")
    op.execute("DROP TABLE IF EXISTS icij_entities")
    op.execute("DROP TABLE IF EXISTS pep_persons")
    op.execute("DROP TABLE IF EXISTS sanctions")
    op.execute("DROP TABLE IF EXISTS streaming_checkpoints")
    op.execute("DROP TABLE IF EXISTS officers_fetch_queue")
    op.execute("DROP TABLE IF EXISTS directorships")
    op.execute("DROP TABLE IF EXISTS psc_ownerships")
    op.execute("DROP TABLE IF EXISTS legal_entities")
    op.execute("DROP TABLE IF EXISTS persons")
    op.execute("DROP TABLE IF EXISTS companies")
    op.execute("DROP TABLE IF EXISTS geo_postcode_centroids")
    op.execute("DROP TABLE IF EXISTS data_sources")
