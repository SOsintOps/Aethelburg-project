-- Runs automatically on the first start of the PostgreSQL container
-- Creates the extensions the aethelburg database needs

\c aethelburg;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Search path for AGE (needed by Cypher queries)
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Create the AGE graph
SELECT create_graph('aethelburg');

-- Separate casework schema
CREATE SCHEMA IF NOT EXISTS casework;
