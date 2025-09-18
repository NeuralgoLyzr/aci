-- ACI Database Schema Creation Script
-- Run this manually in your PostgreSQL database instead of using Alembic migrations

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Create custom types (enums)
CREATE TYPE visibility AS ENUM ('PUBLIC', 'PRIVATE');
CREATE TYPE entitytype AS ENUM ('ENTITY', 'USER', 'ORGANIZATION');
CREATE TYPE protocol AS ENUM ('REST');
CREATE TYPE subscriptionplan AS ENUM ('CUSTOM', 'FREE', 'PRO', 'ENTERPRISE');

-- Create entities table
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    type entitytype NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    profile_picture TEXT,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create apps table
CREATE TABLE apps (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    version VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    logo TEXT,
    categories VARCHAR[] NOT NULL,
    visibility visibility NOT NULL,
    active BOOLEAN NOT NULL,
    security_schemes JSON NOT NULL,
    default_security_credentials_by_scheme JSON NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create functions table
CREATE TABLE functions (
    id UUID PRIMARY KEY,
    app_id UUID NOT NULL REFERENCES apps(id),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    tags VARCHAR[] NOT NULL,
    visibility visibility NOT NULL,
    active BOOLEAN NOT NULL,
    protocol protocol NOT NULL,
    protocol_data JSON NOT NULL,
    parameters JSON NOT NULL,
    response JSON NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create organizations table
CREATE TABLE organizations (
    id UUID PRIMARY KEY REFERENCES entities(id)
);

-- Create projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES entities(id),
    name VARCHAR(255) NOT NULL,
    visibility_access visibility NOT NULL,
    daily_quota_used INTEGER NOT NULL,
    daily_quota_reset_at TIMESTAMP DEFAULT NOW() NOT NULL,
    total_quota_used INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create subscriptions table
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES entities(id),
    plan subscriptionplan NOT NULL,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create agents table
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    allowed_apps VARCHAR[] NOT NULL,
    custom_instructions JSON NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create api_keys table
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    hashed_key VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create app_configurations table
CREATE TABLE app_configurations (
    id UUID PRIMARY KEY,
    app_name VARCHAR(100) NOT NULL REFERENCES apps(name),
    entity_id UUID NOT NULL REFERENCES entities(id),
    security_scheme VARCHAR(255) NOT NULL,
    security_credentials JSON NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(app_name, entity_id, security_scheme)
);

-- Create function_executions table
CREATE TABLE function_executions (
    id UUID PRIMARY KEY,
    function_name VARCHAR(255) NOT NULL REFERENCES functions(name),
    agent_id UUID NOT NULL REFERENCES agents(id),
    input_data JSON NOT NULL,
    output_data JSON,
    status VARCHAR(50) NOT NULL,
    error_message TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create alembic_version table (required for Alembic to track migrations)
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

-- Insert the current migration version
INSERT INTO alembic_version (version_num) VALUES ('c6f47d7d2fa1');

-- Create indexes for better performance
CREATE INDEX idx_apps_name ON apps(name);
CREATE INDEX idx_functions_name ON functions(name);
CREATE INDEX idx_functions_app_id ON functions(app_id);
CREATE INDEX idx_projects_owner_id ON projects(owner_id);
CREATE INDEX idx_agents_project_id ON agents(project_id);
CREATE INDEX idx_api_keys_agent_id ON api_keys(agent_id);
CREATE INDEX idx_api_keys_hashed_key ON api_keys(hashed_key);
CREATE INDEX idx_app_configurations_app_name ON app_configurations(app_name);
CREATE INDEX idx_app_configurations_entity_id ON app_configurations(entity_id);
CREATE INDEX idx_function_executions_function_name ON function_executions(function_name);
CREATE INDEX idx_function_executions_agent_id ON function_executions(agent_id);

-- Grant permissions (adjust as needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
