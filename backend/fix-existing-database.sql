-- Fix existing database by dropping and recreating problematic tables
-- This script handles the case where tables exist but have wrong schema

-- Create the missing security scheme enum if it doesn't exist
DO $$ BEGIN
    CREATE TYPE securityscheme AS ENUM ('NO_AUTH', 'API_KEY', 'HTTP_BASIC', 'HTTP_BEARER', 'OAUTH2');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Drop the problematic app_configurations table (it has wrong columns)
DROP TABLE IF EXISTS app_configurations CASCADE;

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

-- Create indexes for app_configurations
CREATE INDEX IF NOT EXISTS idx_app_configurations_project_id ON app_configurations(project_id);
CREATE INDEX IF NOT EXISTS idx_app_configurations_app_id ON app_configurations(app_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
