"""
Run database migrations at startup if RUN_MIGRATIONS environment variable is set to 'true'.
This ensures the database schema is up-to-date before the server starts.
"""

import os
import subprocess
import sys
from pathlib import Path

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def run_migrations() -> None:
    """Run Alembic migrations to upgrade database to latest version."""
    
    # Check if migrations should run
    should_run = os.getenv("RUN_MIGRATIONS", "false").lower() == "true"
    
    if not should_run:
        logger.info("Skipping database migrations (RUN_MIGRATIONS not set to 'true')")
        return
    
    logger.info("🔄 Running database migrations...")
    
    try:
        # Get the backend directory (where alembic.ini is located)
        backend_dir = Path(__file__).parent.parent.parent
        alembic_ini = backend_dir / "alembic.ini"
        
        if not alembic_ini.exists():
            logger.error(f"❌ alembic.ini not found at {alembic_ini}")
            raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")
        
        logger.info(f"Using alembic.ini at: {alembic_ini}")
        
        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "-c", str(alembic_ini), "upgrade", "head"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        
        # Log output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(f"[Alembic] {line}")
        
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():  # Only log non-empty lines
                    logger.warning(f"[Alembic] {line}")
        
        # Check if migration succeeded
        if result.returncode == 0:
            logger.info("✅ Database migrations completed successfully")
        else:
            logger.error(f"❌ Database migrations failed with exit code {result.returncode}")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            raise RuntimeError(f"Alembic migration failed with exit code {result.returncode}")
            
    except FileNotFoundError as e:
        logger.error(f"❌ Migration failed: {e}")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Migration command failed: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error during migration: {e}")
        raise


def check_migration_status() -> None:
    """Check current migration status without running migrations."""
    try:
        backend_dir = Path(__file__).parent.parent.parent
        alembic_ini = backend_dir / "alembic.ini"
        
        if not alembic_ini.exists():
            logger.warning(f"⚠️  alembic.ini not found at {alembic_ini}")
            return
        
        # Run alembic current to show current revision
        result = subprocess.run(
            ["alembic", "-c", str(alembic_ini), "current"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode == 0 and result.stdout:
            logger.info(f"📊 Current database revision: {result.stdout.strip()}")
        else:
            logger.warning("⚠️  Could not determine current database revision")
            
    except Exception as e:
        logger.warning(f"⚠️  Could not check migration status: {e}")


if __name__ == "__main__":
    # Allow running this script directly for testing
    run_migrations()
