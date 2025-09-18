-- Complete ACI Database Schema (Generated from Latest Alembic Migrations)
-- This includes ALL migrations up to the latest version

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Create custom types (enums)
DO $$ BEGIN
    CREATE TYPE visibility AS ENUM ('PUBLIC', 'PRIVATE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE entitytype AS ENUM ('ENTITY', 'USER', 'ORGANIZATION');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE protocol AS ENUM ('REST', 'CONNECTOR', 'rest', 'connector');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE subscriptionplan AS ENUM ('CUSTOM', 'FREE', 'PRO', 'ENTERPRISE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE securityscheme AS ENUM ('NO_AUTH', 'API_KEY', 'HTTP_BASIC', 'HTTP_BEARER', 'OAUTH2');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE stripesubscriptionstatus AS ENUM ('INCOMPLETE', 'INCOMPLETE_EXPIRED', 'TRIALING', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'UNPAID', 'PAUSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE stripesubscriptioninterval AS ENUM ('MONTH', 'YEAR');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE websiteevaluationstatus AS ENUM ('IN_PROGRESS', 'COMPLETED', 'FAILED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create apps table
CREATE TABLE IF NOT EXISTS apps (
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
    security_schemes JSONB NOT NULL,
    default_security_credentials_by_scheme JSONB NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create entities table
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY,
    type entitytype NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    profile_picture TEXT,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY REFERENCES entities(id)
);

-- Create projects table (updated schema)
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    visibility_access visibility NOT NULL,
    daily_quota_used INTEGER NOT NULL DEFAULT 0,
    daily_quota_reset_at TIMESTAMP DEFAULT NOW() NOT NULL,
    total_quota_used INTEGER NOT NULL DEFAULT 0,
    api_quota_monthly_used INTEGER DEFAULT 0,
    api_quota_last_reset TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create functions table
CREATE TABLE IF NOT EXISTS functions (
    id UUID PRIMARY KEY,
    app_id UUID NOT NULL REFERENCES apps(id),
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    protocol protocol NOT NULL,
    protocol_data JSONB NOT NULL,
    parameters JSONB NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(app_id, name)
);

-- Create agents table
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    allowed_apps VARCHAR[] NOT NULL,
    excluded_apps VARCHAR[] NOT NULL DEFAULT '{}',
    excluded_functions VARCHAR[] NOT NULL DEFAULT '{}',
    custom_instructions JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create api_keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    hashed_key VARCHAR(255) NOT NULL UNIQUE,
    encrypted_key TEXT NOT NULL,
    key_hmac TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create app_configurations table (CORRECT SCHEMA)
CREATE TABLE IF NOT EXISTS app_configurations (
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

-- Create function_executions table
CREATE TABLE IF NOT EXISTS function_executions (
    id UUID PRIMARY KEY,
    function_name VARCHAR(255) NOT NULL REFERENCES functions(name),
    agent_id UUID NOT NULL REFERENCES agents(id),
    input_data JSONB NOT NULL,
    output_data JSONB NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create linked_accounts table
CREATE TABLE IF NOT EXISTS linked_accounts (
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
CREATE TABLE IF NOT EXISTS secrets (
    id UUID PRIMARY KEY,
    linked_account_id UUID NOT NULL REFERENCES linked_accounts(id),
    key VARCHAR(255) NOT NULL,
    value BYTEA NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(linked_account_id, key)
);

-- Create website_evaluations table
CREATE TABLE IF NOT EXISTS website_evaluations (
    id UUID PRIMARY KEY,
    linked_account_id UUID NOT NULL REFERENCES linked_accounts(id),
    url VARCHAR(255) NOT NULL,
    status websiteevaluationstatus NOT NULL,
    result TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(linked_account_id, url)
);

-- Create billing tables
CREATE TABLE IF NOT EXISTS plans (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    stripe_product_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_monthly_price_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_yearly_price_id VARCHAR(255) NOT NULL UNIQUE,
    features JSONB NOT NULL,
    is_public BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_stripe_events (
    id UUID PRIMARY KEY,
    event_id VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL UNIQUE,
    plan_id UUID NOT NULL REFERENCES plans(id),
    stripe_customer_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
    status stripesubscriptionstatus NOT NULL,
    interval stripesubscriptioninterval NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

-- Create alembic_version table
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

-- Insert the latest migration version
INSERT INTO alembic_version (version_num) VALUES ('48bf142a794c')
ON CONFLICT (version_num) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_apps_name ON apps(name);
CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
CREATE INDEX IF NOT EXISTS idx_functions_app_id ON functions(app_id);
CREATE INDEX IF NOT EXISTS idx_projects_org_id ON projects(org_id);
CREATE INDEX IF NOT EXISTS idx_agents_project_id ON agents(project_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_agent_id ON api_keys(agent_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hashed_key ON api_keys(hashed_key);
CREATE INDEX IF NOT EXISTS idx_app_configurations_project_id ON app_configurations(project_id);
CREATE INDEX IF NOT EXISTS idx_app_configurations_app_id ON app_configurations(app_id);
CREATE INDEX IF NOT EXISTS idx_function_executions_function_name ON function_executions(function_name);
CREATE INDEX IF NOT EXISTS idx_function_executions_agent_id ON function_executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_linked_accounts_project_id ON linked_accounts(project_id);
CREATE INDEX IF NOT EXISTS idx_linked_accounts_app_id ON linked_accounts(app_id);
CREATE INDEX IF NOT EXISTS idx_secrets_linked_account_id ON secrets(linked_account_id);
CREATE INDEX IF NOT EXISTS idx_website_evaluations_linked_account_id ON website_evaluations(linked_account_id);
CREATE INDEX IF NOT EXISTS idx_plans_name ON plans(name);
CREATE INDEX IF NOT EXISTS idx_subscriptions_org_id ON subscriptions(org_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_id ON subscriptions(plan_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
