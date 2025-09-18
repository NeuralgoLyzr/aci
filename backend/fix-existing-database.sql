-- Fix existing database by dropping and recreating problematic tables
-- This script handles the case where tables exist but have wrong schema

-- Create the missing security scheme enum if it doesn't exist
DO $$ BEGIN
    CREATE TYPE securityscheme AS ENUM ('NO_AUTH', 'API_KEY', 'HTTP_BASIC', 'HTTP_BEARER', 'OAUTH2');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Drop problematic tables that might have wrong columns
DROP TABLE IF EXISTS app_configurations CASCADE;
DROP TABLE IF EXISTS linked_accounts CASCADE;
DROP TABLE IF EXISTS secrets CASCADE;
DROP TABLE IF EXISTS website_evaluations CASCADE;

-- Create missing enum types
DO $$ BEGIN
    CREATE TYPE websiteevaluationstatus AS ENUM ('IN_PROGRESS', 'COMPLETED', 'FAILED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Recreate app_configurations table with correct schema
CREATE TABLE app_configurations (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    app_id UUID NOT NULL REFERENCES apps(id),
    security_scheme securityscheme NOT NULL,
    security_scheme_overrides JSONB NOT NULL,
    enabled BOOLEAN NOT NULL,
    all_functions_enabled BOOLEAN NOT NULL,
    enabled_functions VARCHAR[] NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(project_id, app_id)
);

-- Create linked_accounts table
CREATE TABLE linked_accounts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    app_id UUID NOT NULL REFERENCES apps(id),
    linked_account_owner_id VARCHAR(255) NOT NULL,
    security_scheme securityscheme NOT NULL,
    security_credentials JSONB NOT NULL,
    enabled BOOLEAN NOT NULL,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(project_id, app_id, linked_account_owner_id)
);

-- Create secrets table
CREATE TABLE secrets (
    id UUID PRIMARY KEY,
    linked_account_id UUID NOT NULL REFERENCES linked_accounts(id),
    key VARCHAR(255) NOT NULL,
    value BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(linked_account_id, key)
);

-- Create website_evaluations table
CREATE TABLE website_evaluations (
    id UUID PRIMARY KEY,
    linked_account_id UUID NOT NULL REFERENCES linked_accounts(id),
    url VARCHAR(255) NOT NULL,
    status websiteevaluationstatus NOT NULL,
    result TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(linked_account_id, url)
);

-- Create indexes for all tables
CREATE INDEX IF NOT EXISTS idx_app_configurations_project_id ON app_configurations(project_id);
CREATE INDEX IF NOT EXISTS idx_app_configurations_app_id ON app_configurations(app_id);
CREATE INDEX IF NOT EXISTS idx_linked_accounts_project_id ON linked_accounts(project_id);
CREATE INDEX IF NOT EXISTS idx_linked_accounts_app_id ON linked_accounts(app_id);
CREATE INDEX IF NOT EXISTS idx_secrets_linked_account_id ON secrets(linked_account_id);
CREATE INDEX IF NOT EXISTS idx_website_evaluations_linked_account_id ON website_evaluations(linked_account_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
