-- =============================================================================
-- LMIS PostgreSQL Initialization Script
-- =============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fuzzy text matching for ontology lookup
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- GIN indexes on composite types

-- Create application schema
CREATE SCHEMA IF NOT EXISTS lmis;

-- Set search path
ALTER DATABASE lmis_db SET search_path TO lmis, public;
