"""
Simple schema fixes that run at startup.
This handles any schema mismatches without complex migrations.
"""

import os
from pathlib import Path

from aci.common.logging_setup import get_logger
from aci.common.utils import create_db_session
from aci.server import config as server_config

logger = get_logger(__name__)


def fix_schema() -> None:
    """Fix any schema issues at startup."""
    
    # Check if schema fixes should run - default to true
    should_run = os.getenv("RUN_SCHEMA_FIXES", "true").lower() == "true"
    
    if not should_run:
        logger.info("Skipping schema fixes (RUN_SCHEMA_FIXES explicitly set to false)")
        return
    
    logger.info("Running schema fixes (RUN_SCHEMA_FIXES is true or not set)")
    
    logger.info("🔧 Running schema fixes...")
    
    try:
        with create_db_session(server_config.get_db_full_url_sync()) as db:
            
            # Fix 1: Add api_key_id columns for API key ownership
            logger.info("Adding api_key_id columns for API key ownership...")
            try:
                # Add api_key_id to apps table
                db.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'apps' 
                            AND column_name = 'api_key_id'
                        ) THEN
                            ALTER TABLE apps ADD COLUMN api_key_id UUID NULL;
                            ALTER TABLE apps ADD CONSTRAINT fk_apps_api_key_id 
                                FOREIGN KEY (api_key_id) REFERENCES api_keys(id);
                        END IF;
                    END $$
                """)
                
                # Add api_key_id to functions table
                db.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'functions' 
                            AND column_name = 'api_key_id'
                        ) THEN
                            ALTER TABLE functions ADD COLUMN api_key_id UUID NULL;
                            ALTER TABLE functions ADD CONSTRAINT fk_functions_api_key_id 
                                FOREIGN KEY (api_key_id) REFERENCES api_keys(id);
                        END IF;
                    END $$
                """)
                
                db.commit()
                logger.info("✅ Added api_key_id columns for API key ownership")
            except Exception as e:
                logger.warning(f"Could not add api_key_id columns: {e}")
                db.rollback()
            
            # Fix 2: Ensure all required tables exist with correct schema
            logger.info("Ensuring required tables exist...")
            
            # Create subscriptions table if it doesn't exist
            try:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        org_id VARCHAR(255) NOT NULL UNIQUE,
                        plan_id UUID NOT NULL,
                        stripe_customer_id VARCHAR(255) NOT NULL UNIQUE,
                        stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
                        status VARCHAR(50) NOT NULL,
                        interval VARCHAR(20) NOT NULL,
                        current_period_end TIMESTAMP NOT NULL,
                        cancel_at_period_end BOOLEAN NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Create plans table if it doesn't exist
                db.execute("""
                    CREATE TABLE IF NOT EXISTS plans (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name VARCHAR(255) NOT NULL UNIQUE,
                        stripe_product_id VARCHAR(255) NOT NULL UNIQUE,
                        stripe_monthly_price_id VARCHAR(255) NOT NULL UNIQUE,
                        stripe_yearly_price_id VARCHAR(255) NOT NULL UNIQUE,
                        features JSONB NOT NULL,
                        is_public BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Add foreign key if it doesn't exist
                db.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints 
                            WHERE constraint_name = 'subscriptions_plan_id_fkey'
                        ) THEN
                            ALTER TABLE subscriptions 
                            ADD CONSTRAINT subscriptions_plan_id_fkey 
                            FOREIGN KEY (plan_id) REFERENCES plans(id);
                        END IF;
                    END $$
                """)
                
                # Insert default plans if they don't exist
                db.execute("""
                    INSERT INTO plans (name, stripe_product_id, stripe_monthly_price_id, stripe_yearly_price_id, features, is_public)
                    VALUES 
                        ('starter', 'prod_starter', 'price_starter_monthly', 'price_starter_yearly', 
                         '{"projects": 5, "agents": 10, "linked_accounts": 50, "api_calls_monthly": 10000}', true),
                        ('team', 'prod_team', 'price_team_monthly', 'price_team_yearly', 
                         '{"projects": 50, "agents": 100, "linked_accounts": 500, "api_calls_monthly": 100000}', true)
                    ON CONFLICT (name) DO NOTHING
                """)
                
                db.commit()
                logger.info("✅ Ensured required tables exist")
                
            except Exception as e:
                logger.warning(f"Could not ensure tables exist: {e}")
                db.rollback()
            
        logger.info("✅ Schema fixes completed successfully")
            
    except Exception as e:
        logger.error(f"❌ Schema fixes failed: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Don't raise - let the server start anyway
        logger.warning("Continuing startup despite schema fix errors...")


if __name__ == "__main__":
    # Allow running this script directly for testing
    fix_schema()
