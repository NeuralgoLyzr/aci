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
        response = requests.get(f"{url}/seeding-status", timeout=30)
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
        response = requests.post(f"{url}/seeding-status", 
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
        url = get_lambda_seeding_url()
        response = requests.get(f"{url}/seeding-scripts", timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("scripts", [])
    except Exception as e:
        logger.error(f"Error getting seeding scripts: {e}")
        return get_default_scripts()


def get_default_scripts() -> List[Dict[str, Any]]:
    """Default seeding scripts (fallback)"""
    return [
        {
            'name': 'run_seed_db_sh',
            'description': 'Run the seed_db.sh script with --all --mock flags',
            'order': 1,
            'enabled': True,
            'type': 'shell'
        }
    ]


def run_seed_db_script() -> bool:
    """Run the actual seed_db.sh script"""
    try:
        script_path = Path("/workdir/scripts/seed_db.sh")
        
        if not script_path.exists():
            logger.error(f"seed_db.sh script not found at {script_path}")
            return False
        
        logger.info("Running seed_db.sh script with --all --mock flags...")
        
        # Change to workdir to ensure proper paths
        original_cwd = os.getcwd()
        os.chdir("/workdir")
        
        try:
            # Run the seed script with --all --mock flags
            result = subprocess.run(
                ["bash", "scripts/seed_db.sh", "--all", "--mock"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info("seed_db.sh completed successfully")
                logger.info(f"Script output: {result.stdout}")
                return True
            else:
                logger.error(f"seed_db.sh failed with return code {result.returncode}")
                logger.error(f"Script stderr: {result.stderr}")
                logger.error(f"Script stdout: {result.stdout}")
                return False
                
        finally:
            # Restore original working directory
            os.chdir(original_cwd)
            
    except subprocess.TimeoutExpired:
        logger.error("seed_db.sh script timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Error running seed_db.sh script: {e}")
        return False


# Removed create_mock_oauth_secrets - handled by seed_db.sh script


def execute_seeding_script(script: Dict[str, Any]) -> bool:
    """Execute a seeding script"""
    try:
        script_name = script.get('name')
        logger.info(f"Executing seeding script: {script_name}")
        
        if script_name == 'run_seed_db_sh':
            return run_seed_db_script()
        else:
            logger.warning(f"Unknown seeding script: {script_name}")
            return True
            
    except Exception as e:
        logger.error(f"Error executing seeding script {script.get('name')}: {e}")
        return False


# Removed old seeding functions - now using seed_db.sh script directly


def lambda_based_seeding() -> None:
    """Main function to perform Lambda-based seeding"""
    logger.info("Starting Lambda-based seeding check...")
    
    # Skip if environment variable is set
    if os.getenv("SKIP_AUTO_SEED", "false").lower() == "true":
        logger.info("Auto-seeding skipped (SKIP_AUTO_SEED=true)")
        return
    
    # Skip if no Lambda URL provided
    if not os.getenv("SEEDING_LAMBDA_URL"):
        logger.info("No SEEDING_LAMBDA_URL provided, skipping Lambda-based seeding")
        return
    
    try:
        # Check seeding status
        status = check_seeding_status()
        is_seeded = status.get("isSeeded", False)
        
        if is_seeded:
            logger.info("Database already seeded according to Lambda, skipping auto-seed")
            return
        
        logger.info("Database not seeded, starting seeding process...")
        
        # Get seeding scripts
        scripts = get_seeding_scripts()
        enabled_scripts = [s for s in scripts if s.get('enabled', True)]
        enabled_scripts.sort(key=lambda x: x.get('order', 999))
        
        logger.info(f"Found {len(enabled_scripts)} enabled seeding scripts")
        
        # Execute scripts
        all_successful = True
        for script in enabled_scripts:
            success = execute_seeding_script(script)
            if not success:
                all_successful = False
                logger.error(f"Seeding script failed: {script.get('name')}")
                break
        
        if all_successful:
            # Update seeding status
            environment = os.getenv("SERVER_ENVIRONMENT", "local")
            update_success = update_seeding_status(True, environment)
            
            if update_success:
                logger.info("Lambda-based seeding completed successfully!")
            else:
                logger.warning("Seeding completed but failed to update Lambda status")
        else:
            logger.error("Some seeding scripts failed")
            
    except Exception as e:
        logger.error(f"Error during Lambda-based seeding: {e}")
        # Don't raise - allow application to continue starting
