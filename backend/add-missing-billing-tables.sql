-- Add missing billing tables to existing database
-- Run this if your database is missing the plans table

-- Create missing enums
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

-- Create billing-related tables
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
    plan_id UUID NOT NULL,
    stripe_customer_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
    status stripesubscriptionstatus NOT NULL,
    interval stripesubscriptioninterval NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_plans_name ON plans(name);
CREATE INDEX IF NOT EXISTS idx_subscriptions_org_id ON subscriptions(org_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan_id ON subscriptions(plan_id);

-- Update migration version
INSERT INTO alembic_version (version_num) VALUES ('068b47f44d83')
ON CONFLICT (version_num) DO UPDATE SET version_num = '068b47f44d83';

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
