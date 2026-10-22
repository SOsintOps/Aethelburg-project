-- =============================================================================
-- Apache AGE Graph Schema for Aethelburg (`aethelburg` graph)
-- Compatible with FollowTheMoney (FtM v3.x) vertex & interval schemas
-- =============================================================================

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Ensure graph exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'aethelburg') THEN
        PERFORM create_graph('aethelburg');
    END IF;
END $$;

-- Vertex Labels (FtM Things)
SELECT create_vlabel('aethelburg', 'Company');
SELECT create_vlabel('aethelburg', 'Person');
SELECT create_vlabel('aethelburg', 'LegalEntity');
SELECT create_vlabel('aethelburg', 'Address');
SELECT create_vlabel('aethelburg', 'Sanction');
SELECT create_vlabel('aethelburg', 'OffshoreEntity');

-- Edge Labels (FtM Intervals & Links)
SELECT create_elabel('aethelburg', 'CONTROLS');        -- FtM: Ownership
SELECT create_elabel('aethelburg', 'DIRECTS');         -- FtM: Directorship
SELECT create_elabel('aethelburg', 'REGISTERED_AT');   -- Company -> Address
SELECT create_elabel('aethelburg', 'SANCTIONED_AS');   -- Entity -> Sanction
SELECT create_elabel('aethelburg', 'OFFSHORE_MATCH');  -- UK Entity -> ICIJ OffshoreEntity
