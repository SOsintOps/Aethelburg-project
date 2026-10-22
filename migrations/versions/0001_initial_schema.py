"""Schema iniziale Aethelburg — ontologia v2.0.0 (FollowTheMoney v3.x compatible)

Revision ID: 0001
Revises:
Create Date: 2026-03-26

Crea:
  - Tabella canonica ftm_entities (FollowTheMoney v3.x JSONB + indice GIN)
  - Schema public: tabelle dati sorgente (Addresses, Companies House, PSC, ICIJ, Sanctions, PEP, Geo)
  - Schema casework: tabelle investigative allineate con Intelligence Field Notes (UNODC 4x4, confidence)
  - Estensioni: postgis, vector, age, pg_trgm, unaccent, uuid-ossp
  - Indici critici per performance
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

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
    # TABELLA: ftm_entities — FollowTheMoney v3.x Canonical Entity Store  #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE ftm_entities (
        id              VARCHAR(128) PRIMARY KEY,
        schema          VARCHAR(64)  NOT NULL,
        caption         VARCHAR(500) NOT NULL,
        properties      JSONB        NOT NULL DEFAULT '{}',
        datasets        TEXT[]       NOT NULL DEFAULT '{}',
        referents       TEXT[]       NOT NULL DEFAULT '{}',
        target          BOOLEAN      NOT NULL DEFAULT false,
        first_seen      TIMESTAMPTZ  NOT NULL DEFAULT now(),
        last_seen       TIMESTAMPTZ  NOT NULL DEFAULT now(),
        last_change     TIMESTAMPTZ  NOT NULL DEFAULT now(),
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_ftm_entities_schema ON ftm_entities(schema)")
    op.execute("CREATE INDEX idx_ftm_entities_caption ON ftm_entities USING gin(to_tsvector('simple', caption))")
    op.execute("CREATE INDEX idx_ftm_entities_props ON ftm_entities USING gin(properties)")
    op.execute("CREATE INDEX idx_ftm_entities_datasets ON ftm_entities USING gin(datasets)")
    op.execute("CREATE INDEX idx_ftm_entities_target ON ftm_entities(target) WHERE target = true")

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
        precision       VARCHAR(10),
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_geo_postcode_geom ON geo_postcode_centroids USING gist(geom)")

    # ------------------------------------------------------------------ #
    # TABELLA: addresses — Indirizzi normalizzati (FtM: Address)          #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE addresses (
        id                  VARCHAR(128) PRIMARY KEY,
        ftm_id              VARCHAR(128) UNIQUE NOT NULL,
        ftm_schema          VARCHAR(64)  NOT NULL DEFAULT 'Address',
        full_address        TEXT         NOT NULL,
        street              VARCHAR(300),
        city                VARCHAR(100),
        county              VARCHAR(100),
        postcode            VARCHAR(20),
        country             VARCHAR(100),
        country_code        VARCHAR(10),
        address_fingerprint VARCHAR(200) UNIQUE,
        lat                 DOUBLE PRECISION,
        lon                 DOUBLE PRECISION,
        company_count       INTEGER NOT NULL DEFAULT 0,
        source_id           UUID REFERENCES data_sources(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_addresses_postcode ON addresses(postcode)")
    op.execute("CREATE INDEX idx_addresses_fp ON addresses(address_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: companies — Companies House bulk data (FtM: Company)       #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE companies (
        company_number          VARCHAR(8)   PRIMARY KEY,
        company_name            VARCHAR(500) NOT NULL,
        ftm_id                  VARCHAR(128),
        ftm_schema              VARCHAR(64)  NOT NULL DEFAULT 'Company',

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

        -- Codici SIC
        sic_text_1  VARCHAR(200),
        sic_text_2  VARCHAR(200),
        sic_text_3  VARCHAR(200),
        sic_text_4  VARCHAR(200),
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
        address_fingerprint     VARCHAR(200),
        name_fingerprint        VARCHAR(500),
        risk_score              FLOAT DEFAULT 0.0,
        ft3_techniques          VARCHAR(20)[],
        officers_fetched_at     TIMESTAMPTZ,
        is_flagged              BOOLEAN DEFAULT false,

        -- Provenance
        source_id       UUID REFERENCES data_sources(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("CREATE INDEX idx_companies_name ON companies USING gin(to_tsvector('simple', company_name))")
    op.execute("CREATE INDEX idx_companies_fingerprint ON companies(name_fingerprint)")
    op.execute("CREATE INDEX idx_companies_postcode ON companies(reg_address_postcode)")
    op.execute("CREATE INDEX idx_companies_addr_fp ON companies(address_fingerprint)")
    op.execute("CREATE INDEX idx_companies_status ON companies(company_status)")
    op.execute("CREATE INDEX idx_companies_risk ON companies(risk_score DESC) WHERE is_flagged = true")
    op.execute("CREATE INDEX idx_companies_sic1 ON companies(sic_code_1)")
    op.execute("CREATE INDEX idx_companies_incorporation ON companies(incorporation_date)")
    op.execute("CREATE INDEX idx_companies_ftm_id ON companies(ftm_id)")

    # ------------------------------------------------------------------ #
    # TABELLA: persons — persone fisiche (FtM: Person)                    #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE persons (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ftm_id                  VARCHAR(128),
        ftm_schema              VARCHAR(64) NOT NULL DEFAULT 'Person',
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
        pep_source              VARCHAR(50),
        source_id               UUID REFERENCES data_sources(id),
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_persons_fingerprint ON persons(name_fingerprint)")
    op.execute("CREATE INDEX idx_persons_name_fts ON persons USING gin(to_tsvector('simple', name))")
    op.execute("CREATE INDEX idx_persons_pep ON persons(is_pep) WHERE is_pep = true")
    op.execute("CREATE INDEX idx_persons_ftm_id ON persons(ftm_id)")

    # ------------------------------------------------------------------ #
    # TABELLA: legal_entities — PSC corporate, entità straniere           #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE legal_entities (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ftm_id                  VARCHAR(128),
        ftm_schema              VARCHAR(64) NOT NULL DEFAULT 'LegalEntity',
        name                    VARCHAR(500) NOT NULL,
        name_fingerprint        VARCHAR(500),
        jurisdiction            VARCHAR(100),
        company_number_foreign  VARCHAR(100),
        entity_type             VARCHAR(50),
        is_offshore             BOOLEAN DEFAULT false,
        source_id               UUID REFERENCES data_sources(id),
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_legal_entities_fingerprint ON legal_entities(name_fingerprint)")
    op.execute("CREATE INDEX idx_legal_entities_jurisdiction ON legal_entities(jurisdiction)")
    op.execute("CREATE INDEX idx_legal_entities_ftm_id ON legal_entities(ftm_id)")

    # ------------------------------------------------------------------ #
    # TABELLA: psc_ownerships — PSC ownership stakes (FtM: Ownership)     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE psc_ownerships (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ftm_id              VARCHAR(128),
        ftm_schema          VARCHAR(64) NOT NULL DEFAULT 'Ownership',
        company_number      VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        person_id           UUID REFERENCES persons(id),
        legal_entity_id     UUID REFERENCES legal_entities(id),
        nature_of_control   VARCHAR(100)[],
        notified_on         DATE,
        ceased_on           DATE,
        is_ceased           BOOLEAN DEFAULT false,
        is_super_secure     BOOLEAN DEFAULT false,
        source_id           UUID REFERENCES data_sources(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chk_psc_owner CHECK (
            (person_id IS NOT NULL AND legal_entity_id IS NULL) OR
            (person_id IS NULL AND legal_entity_id IS NOT NULL) OR
            (is_super_secure = true)
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
        ftm_id              VARCHAR(128),
        ftm_schema          VARCHAR(64) NOT NULL DEFAULT 'Directorship',
        company_number      VARCHAR(8) NOT NULL REFERENCES companies(company_number),
        person_id           UUID REFERENCES persons(id),
        officer_role        VARCHAR(100),
        appointed_on        DATE,
        resigned_on         DATE,
        is_active           BOOLEAN DEFAULT true,
        occupation          VARCHAR(200),
        nationality         VARCHAR(100),
        country_of_residence VARCHAR(100),
        api_person_id       VARCHAR(100),
        source_id           UUID REFERENCES data_sources(id),
        fetched_via         VARCHAR(20),
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
        priority        SMALLINT DEFAULT 5,
        status          VARCHAR(20) DEFAULT 'pending',
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
        stream_type     VARCHAR(50) PRIMARY KEY,
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
    # TABELLA: sanctions — entità sanzionate (FtM: Sanction + Entity)     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE sanctions (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ftm_id                  VARCHAR(128),
        ftm_schema              VARCHAR(64) NOT NULL DEFAULT 'Sanction',
        subject_ftm_id          VARCHAR(128),
        name                    VARCHAR(500) NOT NULL,
        name_fingerprint        VARCHAR(500),
        aliases                 TEXT[],
        entity_type             VARCHAR(50),
        topics                  VARCHAR(50)[],
        countries               VARCHAR(50)[],
        registration_numbers    TEXT[],
        list_name               VARCHAR(100),
        listed_on               DATE,
        source                  VARCHAR(50),
        opensanctions_id        VARCHAR(100),
        raw_properties          JSONB,
        source_id               UUID REFERENCES data_sources(id),
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE INDEX idx_sanctions_fingerprint ON sanctions(name_fingerprint)")
    op.execute("CREATE INDEX idx_sanctions_topics ON sanctions USING gin(topics)")
    op.execute("CREATE INDEX idx_sanctions_regnums ON sanctions USING gin(registration_numbers)")
    op.execute("CREATE INDEX idx_sanctions_name_fts ON sanctions USING gin(to_tsvector('simple', name))")

    # ------------------------------------------------------------------ #
    # TABELLA: pep_persons — Politically Exposed Persons                   #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE pep_persons (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'Person',
        name            VARCHAR(500) NOT NULL,
        name_fingerprint VARCHAR(500),
        country         VARCHAR(10),
        party           VARCHAR(200),
        legislature     VARCHAR(200),
        mandate_start   DATE,
        mandate_end     DATE,
        is_current      BOOLEAN DEFAULT false,
        pep_source      VARCHAR(50) NOT NULL,
        external_id     VARCHAR(200),
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
        entity_id       VARCHAR(128) NOT NULL,
        entity_type     VARCHAR(30) NOT NULL,
        variant_text    VARCHAR(500) NOT NULL,
        fingerprint     VARCHAR(500),
        ftm_id          VARCHAR(128),
        variant_type    VARCHAR(30),
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
        node_id         VARCHAR(50) PRIMARY KEY,
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'Company',
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
        source_id_list  VARCHAR(200),
        valid_until     VARCHAR(100),
        note            TEXT,
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_entities_fp ON icij_entities(name_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_officers — ICIJ officers/shareholders                 #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_officers (
        node_id         VARCHAR(50) PRIMARY KEY,
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'LegalEntity',
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
    # TABELLA: icij_intermediaries — ICIJ intermediaries                  #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_intermediaries (
        node_id         VARCHAR(50) PRIMARY KEY,
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'LegalEntity',
        name            VARCHAR(500),
        name_fingerprint VARCHAR(500),
        status          VARCHAR(100),
        internal_id     VARCHAR(100),
        address         TEXT,
        countries       VARCHAR(500),
        country_codes   VARCHAR(200),
        source_id_list  VARCHAR(200),
        valid_until     VARCHAR(100),
        note            TEXT,
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_intermediaries_fp ON icij_intermediaries(name_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_addresses — ICIJ addresses                            #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_addresses (
        node_id             VARCHAR(50) PRIMARY KEY,
        ftm_id              VARCHAR(128),
        ftm_schema          VARCHAR(64) NOT NULL DEFAULT 'Address',
        address             TEXT,
        name                VARCHAR(500),
        countries           VARCHAR(500),
        country_codes       VARCHAR(200),
        address_fingerprint VARCHAR(200),
        source_id_list      VARCHAR(200),
        valid_until         VARCHAR(100),
        note                TEXT,
        source_id           UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_addresses_fp ON icij_addresses(address_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_others — ICIJ other nodes                             #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_others (
        node_id         VARCHAR(50) PRIMARY KEY,
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'LegalEntity',
        name            VARCHAR(500),
        name_fingerprint VARCHAR(500),
        type            VARCHAR(200),
        incorporation_date DATE,
        struck_off_date DATE,
        closed_date     DATE,
        jurisdiction    VARCHAR(200),
        jurisdiction_description VARCHAR(200),
        countries       VARCHAR(500),
        country_codes   VARCHAR(200),
        source_id_list  VARCHAR(200),
        valid_until     VARCHAR(100),
        note            TEXT,
        source_id       UUID REFERENCES data_sources(id)
    )
    """)
    op.execute("CREATE INDEX idx_icij_others_fp ON icij_others(name_fingerprint)")

    # ------------------------------------------------------------------ #
    # TABELLA: icij_relationships — ICIJ relationship edges               #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE TABLE icij_relationships (
        id              BIGSERIAL PRIMARY KEY,
        ftm_id          VARCHAR(128),
        ftm_schema      VARCHAR(64) NOT NULL DEFAULT 'UnknownLink',
        node_id_start   VARCHAR(50) NOT NULL,
        node_id_end     VARCHAR(50) NOT NULL,
        rel_type        VARCHAR(100),
        link            VARCHAR(200),
        status          VARCHAR(100),
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
        ft3_technique       VARCHAR(20) NOT NULL,
        priority            VARCHAR(10) NOT NULL,
        score_contribution  FLOAT NOT NULL DEFAULT 0.0,
        evidence            JSONB NOT NULL DEFAULT '{}',
        source_ids          UUID[],
        detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
        is_active           BOOLEAN NOT NULL DEFAULT true,
        UNIQUE (company_number, ft3_technique)
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
        event_type      VARCHAR(50) NOT NULL,
        entity_type     VARCHAR(30) NOT NULL,
        entity_id       VARCHAR(100) NOT NULL,
        old_value       JSONB,
        new_value       JSONB,
        detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        source          VARCHAR(50)
    )
    """)
    op.execute("CREATE INDEX idx_events_entity ON entity_events(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_events_type ON entity_events(event_type)")
    op.execute("CREATE INDEX idx_events_date ON entity_events(detected_at DESC)")

    # ------------------------------------------------------------------ #
    # SCHEMA CASEWORK — investigazioni (ADR-012 + Intelligence Notes)      #
    # ------------------------------------------------------------------ #

    op.execute("""
    CREATE TABLE casework.investigations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title           VARCHAR(500) NOT NULL,
        description     TEXT,
        hypothesis      TEXT,
        classification  VARCHAR(30) DEFAULT 'CONFIDENTIAL',
        status          VARCHAR(30) NOT NULL DEFAULT 'open',
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
        entity_type         VARCHAR(30) NOT NULL,
        entity_id           VARCHAR(100) NOT NULL,
        role_in_case        VARCHAR(30) DEFAULT 'subject',
        relevance_note      TEXT,
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
        annotation_type     VARCHAR(30) DEFAULT 'note',
        confidence          VARCHAR(20) DEFAULT 'moderate',
        source_grade        VARCHAR(5)  DEFAULT 'B2',
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
        confidence_level    VARCHAR(20) DEFAULT 'moderate',
        source_grade        VARCHAR(5)  DEFAULT 'C3',
        evidence            TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.visual_snapshots (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID NOT NULL REFERENCES casework.investigations(id) ON DELETE CASCADE,
        title               VARCHAR(300),
        view_type           VARCHAR(30) DEFAULT 'graph',
        snapshot_png_b64    TEXT,
        graph_json          JSONB,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE casework.saved_queries (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        investigation_id    UUID REFERENCES casework.investigations(id) ON DELETE SET NULL,
        title               VARCHAR(300) NOT NULL,
        query_type          VARCHAR(30) NOT NULL,
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
        format              VARCHAR(20) NOT NULL,
        file_path           TEXT,
        file_size_bytes     BIGINT,
        sha256_hash         VARCHAR(64),
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
    op.execute("DROP TABLE IF EXISTS icij_others")
    op.execute("DROP TABLE IF EXISTS icij_addresses")
    op.execute("DROP TABLE IF EXISTS icij_intermediaries")
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
    op.execute("DROP TABLE IF EXISTS addresses")
    op.execute("DROP TABLE IF EXISTS geo_postcode_centroids")
    op.execute("DROP TABLE IF EXISTS ftm_entities")
    op.execute("DROP TABLE IF EXISTS data_sources")
