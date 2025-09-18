"""
Lambda-based seeding module for ECS deployment.
Checks with Lambda API whether seeding is needed, then seeds if required.
"""
import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import requests

# Removed unused imports - now using seed_db.sh script directly
from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def get_lambda_seeding_url() -> str:
    """Get Lambda seeding API URL from environment"""
    url = os.getenv("SEEDING_LAMBDA_URL")
    if not url:
        raise ValueError("SEEDING_LAMBDA_URL environment variable not set")
    return url.rstrip('/')


def check_seeding_status() -> Dict[str, Any]:
    """Check seeding status from Lambda API"""
    try:
        url = get_lambda_seeding_url()
        # Your Lambda returns the status directly at the base URL
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error checking seeding status: {e}")
        # Fallback: assume not seeded
        return {"isSeeded": False}


def update_seeding_status(is_seeded: bool, environment: str = "local") -> bool:
    """Update seeding status via Lambda API"""
    try:
        url = get_lambda_seeding_url()
        payload = {
            "isSeeded": is_seeded,
            "environment": environment,
            "seedingVersion": "1.0"
        }
        # Your Lambda expects POST to the base URL
        response = requests.post(url, 
                               json=payload, 
                               timeout=30)
        response.raise_for_status()
        logger.info(f"Successfully updated seeding status: {is_seeded}")
        return True
    except Exception as e:
        logger.error(f"Error updating seeding status: {e}")
        return False


def get_seeding_scripts() -> List[Dict[str, Any]]:
    """Get list of seeding scripts from Lambda API"""
    try:
        # For now, just use default scripts since your Lambda structure is different
        logger.info("Using default seeding scripts")
        return get_default_scripts()
    except Exception as e:
        logger.error(f"Error getting seeding scripts: {e}")
        return get_default_scripts()


def get_default_scripts() -> List[Dict[str, Any]]:
    """Default seeding scripts (fallback)"""
    return [
        {
            'name': 'run_essential_seeding',
            'description': 'Run essential seeding only (faster, no timeout issues)',
            'order': 1,
            'enabled': True,
            'type': 'shell'
        }
    ]


def check_if_schema_exists() -> bool:
    """Check if database schema already exists"""
    try:
        # Build psql command to check if apps table exists
        db_host = os.getenv("SERVER_DB_HOST", "localhost")
        db_user = os.getenv("SERVER_DB_USER", "postgres")
        db_password = os.getenv("SERVER_DB_PASSWORD", "password")
        db_name = os.getenv("SERVER_DB_NAME", "my_app_db")
        db_port = os.getenv("SERVER_DB_PORT", "5432")
        
        # Set password environment variable for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        # Check if apps table exists
        result = subprocess.run(
            [
                "psql", 
                "-h", db_host,
                "-U", db_user,
                "-d", db_name,
                "-p", db_port,
                "-c", "SELECT 1 FROM apps LIMIT 1;",
                "-t"  # tuples only
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )
        
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Error checking schema existence: {e}")
        return False


def ensure_billing_tables_exist() -> bool:
    """Ensure billing tables exist (plans, subscriptions, etc.)"""
    try:
        logger.info("Ensuring billing tables exist...")
        
        billing_file = Path("/workdir/add-missing-billing-tables.sql")
        if not billing_file.exists():
            logger.error(f"Billing tables file not found at {billing_file}")
            return False
        
        # Build psql command
        db_host = os.getenv("SERVER_DB_HOST", "localhost")
        db_user = os.getenv("SERVER_DB_USER", "postgres")
        db_password = os.getenv("SERVER_DB_PASSWORD", "password")
        db_name = os.getenv("SERVER_DB_NAME", "my_app_db")
        db_port = os.getenv("SERVER_DB_PORT", "5432")
        
        # Set password environment variable for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        try:
            # Run psql to execute billing tables creation
            result = subprocess.run(
                [
                    "psql", 
                    "-h", db_host,
                    "-U", db_user,
                    "-d", db_name,
                    "-p", db_port,
                    "-f", str(billing_file)
                ],
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout
                env=env
            )
            
            if result.returncode == 0:
                logger.info("Billing tables ensured successfully")
                logger.info(f"Billing tables output: {result.stdout}")
                return True
            else:
                logger.warning(f"Billing tables creation returned code {result.returncode} but may have succeeded")
                logger.warning(f"Billing tables stderr: {result.stderr}")
                logger.warning(f"Billing tables stdout: {result.stdout}")
                return True  # Consider success even if some warnings
                
        except subprocess.TimeoutExpired:
            logger.error("Billing tables creation timed out after 1 minute")
            return False
            
    except Exception as e:
        logger.error(f"Error ensuring billing tables exist: {e}")
        return False


def create_database_schema() -> bool:
    """Create database schema using SQL script"""
    try:
        # Check if schema already exists
        if check_if_schema_exists():
            logger.info("Database schema already exists, ensuring billing tables exist...")
            return ensure_billing_tables_exist()
            
        logger.info("Creating database schema using SQL script...")
        
        schema_file = Path("/workdir/create-schema.sql")
        if not schema_file.exists():
            logger.error(f"Schema file not found at {schema_file}")
            return False
        
        # Build psql command
        db_host = os.getenv("SERVER_DB_HOST", "localhost")
        db_user = os.getenv("SERVER_DB_USER", "postgres")
        db_password = os.getenv("SERVER_DB_PASSWORD", "password")
        db_name = os.getenv("SERVER_DB_NAME", "my_app_db")
        db_port = os.getenv("SERVER_DB_PORT", "5432")
        
        # Set password environment variable for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        try:
            # Run psql to execute schema creation
            result = subprocess.run(
                [
                    "psql", 
                    "-h", db_host,
                    "-U", db_user,
                    "-d", db_name,
                    "-p", db_port,
                    "-f", str(schema_file)
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
                env=env
            )
            
            if result.returncode == 0:
                logger.info("Database schema created successfully")
                logger.info(f"Schema creation output: {result.stdout}")
                return True
            else:
                logger.warning(f"Schema creation returned code {result.returncode} but may have succeeded")
                logger.warning(f"Schema stderr: {result.stderr}")
                logger.warning(f"Schema stdout: {result.stdout}")
                # Check if schema actually exists now
                return check_if_schema_exists()
                
        except subprocess.TimeoutExpired:
            logger.error("Schema creation timed out after 2 minutes")
            return False
            
    except Exception as e:
        logger.error(f"Error creating database schema: {e}")
        return False


def run_essential_seeding() -> bool:
    """Run essential seeding only (no CONNECTOR apps, faster)"""
    try:
        script_path = Path("/workdir/seed-essential-only.sh")
        
        if not script_path.exists():
            logger.error(f"Essential seeding script not found at {script_path}")
            return False
        
        logger.info("Running essential seeding script...")
        logger.info("This should complete in 1-2 minutes...")
        
        # Change to workdir to ensure proper paths
        original_cwd = os.getcwd()
        os.chdir("/workdir")
        
        try:
            # Run the essential seeding script
            logger.info("Starting subprocess for essential seeding...")
            result = subprocess.run(
                ["bash", "seed-essential-only.sh"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout (should be enough for essential apps)
            )
            
            logger.info(f"Essential seeding subprocess completed with return code: {result.returncode}")
            
            if result.returncode == 0:
                logger.info("Essential seeding completed successfully")
                
                # Extract and log the API key information
                stdout = result.stdout
                logger.info("=== ESSENTIAL SEEDING COMPLETED SUCCESSFULLY ===")
                
                # Look for the API key output in the stdout
                if "Project Id" in stdout and "API Key" in stdout:
                    # Extract the API key section
                    lines = stdout.split('\n')
                    api_key_section = []
                    capture = False
                    
                    for line in lines:
                        if "Project Id" in line or capture:
                            api_key_section.append(line)
                            capture = True
                            if "API Key" in line:
                                break
                    
                    if api_key_section:
                        logger.info("=== API KEY INFORMATION ===")
                        for line in api_key_section:
                            if line.strip():
                                logger.info(line.strip())
                        logger.info("=== USE THIS API KEY FOR TESTING ===")
                
                # Also log the complete output for debugging
                logger.info(f"Complete essential seeding output: {stdout}")
                return True
            else:
                logger.error(f"Essential seeding failed with return code {result.returncode}")
                logger.error(f"Script stderr: {result.stderr}")
                logger.error(f"Script stdout: {result.stdout}")
                return False
                
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            
    except subprocess.TimeoutExpired:
        logger.error("Essential seeding script timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Error running essential seeding script: {e}")
        import traceback
        logger.error(f"Essential seeding traceback: {traceback.format_exc()}")
        return False


def run_seed_db_script() -> bool:
    """Run the actual seed_db.sh script"""
    try:
        script_path = Path("/workdir/scripts/seed_db.sh")
        
        if not script_path.exists():
            logger.error(f"seed_db.sh script not found at {script_path}")
            return False
        
        logger.info("Running seed_db.sh script with --all --mock flags...")
        logger.info("This may take 2-5 minutes to complete...")
        
        # Change to workdir to ensure proper paths
        original_cwd = os.getcwd()
        os.chdir("/workdir")
        
        try:
            # Run the seed script with --all --mock flags
            logger.info("Starting subprocess for seed_db.sh...")
            result = subprocess.run(
                ["bash", "scripts/seed_db.sh", "--all", "--mock"],
                capture_output=True,
                text=True,
                timeout=2000  # 20 minute timeout (for 600+ apps)
            )
            
            logger.info(f"seed_db.sh subprocess completed with return code: {result.returncode}")
            
            if result.returncode == 0:
                logger.info("seed_db.sh completed successfully")
                
                # Extract and log the API key information
                stdout = result.stdout
                logger.info("=== SEEDING COMPLETED SUCCESSFULLY ===")
                
                # Look for the API key output in the stdout
                if "Project Id" in stdout and "API Key" in stdout:
                    # Extract the API key section
                    lines = stdout.split('\n')
                    api_key_section = []
                    capture = False
                    
                    for line in lines:
                        if "Project Id" in line or capture:
                            api_key_section.append(line)
                            capture = True
                            if "API Key" in line:
                                break
                    
                    if api_key_section:
                        logger.info("=== API KEY INFORMATION ===")
                        for line in api_key_section:
                            if line.strip():
                                logger.info(line.strip())
                        logger.info("=== USE THIS API KEY FOR TESTING ===")
                
                # Also log the last part of output for debugging
                logger.info(f"Script output (last 1000 chars): {stdout[-1000:]}")
                return True
            else:
                logger.error(f"seed_db.sh failed with return code {result.returncode}")
                logger.error(f"Script stderr: {result.stderr}")
                logger.error(f"Script stdout (last 1000 chars): {result.stdout[-1000:]}")
                return False
                
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            
    except subprocess.TimeoutExpired:
        logger.error("seed_db.sh script timed out after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"Error running seed_db.sh script: {e}")
        import traceback
        logger.error(f"Seed script traceback: {traceback.format_exc()}")
        return False


# Removed create_mock_oauth_secrets - handled by seed_db.sh script


def execute_seeding_script(script: Dict[str, Any]) -> bool:
    """Execute a seeding script"""
    try:
        script_name = script.get('name')
        logger.info(f"Executing seeding script: {script_name}")
        
        if script_name == 'run_seed_db_sh':
            # First create schema, then seed
            logger.info("Creating database schema first...")
            if not create_database_schema():
                logger.error("Failed to create database schema")
                return False
            
            logger.info("Schema created, now running seeding...")
            return run_seed_db_script()
        elif script_name == 'run_essential_seeding':
            # First create schema, then run essential seeding only
            logger.info("Creating database schema first...")
            if not create_database_schema():
                logger.error("Failed to create database schema")
                return False
            
            logger.info("Schema created, now running essential seeding...")
            return run_essential_seeding()
        else:
            logger.warning(f"Unknown seeding script: {script_name}")
            return True
            
    except Exception as e:
        logger.error(f"Error executing seeding script {script.get('name')}: {e}")
        return False


# Removed old seeding functions - now using seed_db.sh script directly


def lambda_based_seeding() -> None:
    """Main function to perform Lambda-based seeding"""
    logger.info("=== Starting Lambda-based seeding check ===")
    
    # Skip if environment variable is set
    skip_seed = os.getenv("SKIP_AUTO_SEED", "false").lower()
    logger.info(f"SKIP_AUTO_SEED environment variable: {skip_seed}")
    if skip_seed == "true":
        logger.info("Auto-seeding skipped (SKIP_AUTO_SEED=true)")
        return
    
    # Skip if no Lambda URL provided
    lambda_url = os.getenv("SEEDING_LAMBDA_URL")
    logger.info(f"SEEDING_LAMBDA_URL: {lambda_url}")
    if not lambda_url:
        logger.info("No SEEDING_LAMBDA_URL provided, skipping Lambda-based seeding")
        return
    
    try:
        # Check seeding status
        logger.info("Checking seeding status from Lambda...")
        status = check_seeding_status()
        is_seeded = status.get("isSeeded", False)
        logger.info(f"Lambda seeding status: {status}")
        
        if is_seeded:
            logger.info("Database already seeded according to Lambda, skipping auto-seed")
            return
        
        logger.info("Database not seeded, starting seeding process...")
        
        # Get seeding scripts
        logger.info("Getting seeding scripts...")
        scripts = get_seeding_scripts()
        enabled_scripts = [s for s in scripts if s.get('enabled', True)]
        enabled_scripts.sort(key=lambda x: x.get('order', 999))
        
        logger.info(f"Found {len(enabled_scripts)} enabled seeding scripts: {[s.get('name') for s in enabled_scripts]}")
        
        # Execute scripts
        all_successful = True
        for i, script in enumerate(enabled_scripts):
            script_name = script.get('name')
            logger.info(f"Executing script {i+1}/{len(enabled_scripts)}: {script_name}")
            success = execute_seeding_script(script)
            if not success:
                all_successful = False
                logger.error(f"Seeding script failed: {script_name}")
                break
            else:
                logger.info(f"Seeding script completed successfully: {script_name}")
        
        if all_successful:
            # Update seeding status
            environment = os.getenv("SERVER_ENVIRONMENT", "local")
            logger.info(f"All seeding scripts completed, updating Lambda status for environment: {environment}")
            update_success = update_seeding_status(True, environment)
            
            if update_success:
                logger.info("Lambda-based seeding completed successfully!")
            else:
                logger.warning("Seeding completed but failed to update Lambda status")
        else:
            logger.error("Some seeding scripts failed")
            
    except Exception as e:
        logger.error(f"Error during Lambda-based seeding: {e}")
        import traceback
        logger.error(f"Lambda seeding traceback: {traceback.format_exc()}")
        # Don't raise - allow application to continue starting
