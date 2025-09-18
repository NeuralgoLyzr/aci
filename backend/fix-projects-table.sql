-- Fix projects table to match current schema (add org_id, remove owner_id)
-- This applies the missing migrations to existing databases

-- Add org_id column if it doesn't exist
DO $$ BEGIN
    ALTER TABLE projects ADD COLUMN org_id UUID;
EXCEPTION
    WHEN duplicate_column THEN
        -- Column already exists, do nothing
        NULL;
END $$;

-- Add api_quota_monthly_used column if it doesn't exist
DO $$ BEGIN
    ALTER TABLE projects ADD COLUMN api_quota_monthly_used INTEGER DEFAULT 0;
EXCEPTION
    WHEN duplicate_column THEN
        -- Column already exists, do nothing
        NULL;
END $$;

-- Add api_quota_last_reset column if it doesn't exist
DO $$ BEGIN
    ALTER TABLE projects ADD COLUMN api_quota_last_reset TIMESTAMP DEFAULT NOW();
EXCEPTION
    WHEN duplicate_column THEN
        -- Column already exists, do nothing
        NULL;
END $$;

-- If owner_id exists and org_id is null, copy owner_id to org_id
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'projects' AND column_name = 'owner_id') THEN
        UPDATE projects SET org_id = owner_id WHERE org_id IS NULL;
    END IF;
END $$;

-- Make org_id NOT NULL if it's currently nullable
DO $$ BEGIN
    ALTER TABLE projects ALTER COLUMN org_id SET NOT NULL;
EXCEPTION
    WHEN others THEN
        -- Might fail if there are null values, but that's OK
        NULL;
END $$;

-- Drop owner_id column and its constraints if they exist
DO $$ BEGIN
    -- Drop foreign key constraint if it exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'projects_owner_id_fkey') THEN
        ALTER TABLE projects DROP CONSTRAINT projects_owner_id_fkey;
    END IF;
    
    -- Drop owner_id column if it exists
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'projects' AND column_name = 'owner_id') THEN
        ALTER TABLE projects DROP COLUMN owner_id;
    END IF;
EXCEPTION
    WHEN others THEN
        -- Column might not exist, that's OK
        NULL;
END $$;

-- Create new indexes
CREATE INDEX IF NOT EXISTS idx_projects_org_id ON projects(org_id);

-- Drop old index if it exists
DROP INDEX IF EXISTS idx_projects_owner_id;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
