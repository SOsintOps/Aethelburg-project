-- Eseguito automaticamente al primo avvio del container PostgreSQL
-- Crea le estensioni necessarie nel database aethelburg

\c aethelburg;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Carica il search path per AGE (richiesto per Cypher queries)
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Crea il grafo AGE
SELECT create_graph('aethelburg');

-- Crea schema casework separato
CREATE SCHEMA IF NOT EXISTS casework;
