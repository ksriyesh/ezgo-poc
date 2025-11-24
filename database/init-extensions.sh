#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable PostGIS extension
    CREATE EXTENSION IF NOT EXISTS postgis;
    
    -- Enable H3 extension (if available)
    -- Note: H3 extension may not be available in all PostGIS images
    -- The application can work without it, using Python's h3 library instead
    DO \$\$
    BEGIN
        CREATE EXTENSION IF NOT EXISTS h3;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'H3 extension not available, continuing without it';
    END
    \$\$;
    
    -- Verify extensions are installed
    SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'h3');
EOSQL

