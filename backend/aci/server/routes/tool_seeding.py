"""
Tool seeding management endpoint for running CLI seeding commands through the web UI
"""
import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aci.server import dependencies as deps
from aci.common.db import crud

router = APIRouter()


class SeedingRequest(BaseModel):
    app_path: str = Field(..., description="Path to the app.json file (e.g., ./apps/gmail/app.json)")
    functions_path: Optional[str] = Field(None, description="Path to the functions.json file (e.g., ./apps/gmail/functions.json)")
    secrets: Optional[Dict[str, str]] = Field(None, description="Secrets for OAuth2 authentication")
    skip_dry_run: bool = Field(True, description="Whether to skip dry run and apply changes")


class SeedingResponse(BaseModel):
    success: bool
    message: str
    app_id: Optional[str] = None
    function_ids: Optional[List[str]] = None
    errors: Optional[List[str]] = None


class SeedingStatus(BaseModel):
    is_running: bool
    current_operation: Optional[str] = None
    progress: Optional[str] = None


# Global variable to track seeding status
_seeding_status = {
    "is_running": False,
    "current_operation": None,
    "progress": None
}


@router.get("/seeding-status", response_model=SeedingStatus)
async def get_seeding_status() -> SeedingStatus:
    """Get current seeding operation status"""
    return SeedingStatus(**_seeding_status)


@router.post("/seed-tool", response_model=SeedingResponse)
async def seed_tool(
    request: SeedingRequest,
    background_tasks: BackgroundTasks,
    db_session: Session = Depends(deps.yield_db_session),
) -> SeedingResponse:
    """
    Seed a tool by running the CLI commands to upsert app and functions
    """
    global _seeding_status

    if _seeding_status["is_running"]:
        raise HTTPException(status_code=409, detail="Another seeding operation is already running")

    # Validate paths
    app_file_path = Path(request.app_path)
    if not app_file_path.exists():
        raise HTTPException(status_code=404, detail=f"App file not found: {request.app_path}")

    if request.functions_path:
        functions_file_path = Path(request.functions_path)
        if not functions_file_path.exists():
            raise HTTPException(status_code=404, detail=f"Functions file not found: {request.functions_path}")

    # Start seeding in background
    background_tasks.add_task(
        _run_seeding_process,
        request.app_path,
        request.functions_path,
        request.secrets,
        request.skip_dry_run
    )

    return SeedingResponse(
        success=True,
        message="Seeding process started in background",
    )


async def _run_seeding_process(
    app_path: str,
    functions_path: Optional[str],
    secrets: Optional[Dict[str, str]],
    skip_dry_run: bool
) -> None:
    """Run the seeding process in background"""
    global _seeding_status

    _seeding_status["is_running"] = True
    _seeding_status["current_operation"] = "Starting seeding process"
    _seeding_status["progress"] = "0/2"

    errors = []
    app_id = None
    function_ids = []

    try:
        # Create temporary secrets file if secrets provided
        temp_secrets_file = None
        if secrets:
            temp_secrets_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            )
            json.dump(secrets, temp_secrets_file, indent=2)
            temp_secrets_file.close()

        # Step 1: Upsert app
        _seeding_status["current_operation"] = "Upserting app"
        _seeding_status["progress"] = "1/2"

        app_cmd = ["python", "-m", "aci.cli", "upsert-app", "--app-file", app_path]
        if temp_secrets_file:
            app_cmd.extend(["--secrets-file", temp_secrets_file.name])
        if skip_dry_run:
            app_cmd.append("--skip-dry-run")

        result = await asyncio.create_subprocess_exec(
            *app_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/workdir"  # Assuming this runs in the container
        )

        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            error_msg = f"App upsert failed: {stderr.decode()}"
            errors.append(error_msg)
        else:
            output = stdout.decode()
            # Try to extract app ID from output if available
            # The CLI might output the app ID

        # Step 2: Upsert functions (if functions path provided)
        if functions_path and not errors:
            _seeding_status["current_operation"] = "Upserting functions"
            _seeding_status["progress"] = "2/2"

            functions_cmd = [
                "python", "-m", "aci.cli", "upsert-functions",
                "--functions-file", functions_path
            ]
            if skip_dry_run:
                functions_cmd.append("--skip-dry-run")

            result = await asyncio.create_subprocess_exec(
                *functions_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/workdir"
            )

            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                error_msg = f"Functions upsert failed: {stderr.decode()}"
                errors.append(error_msg)
            else:
                output = stdout.decode()
                # Try to extract function IDs from output if available

        # Clean up temp file
        if temp_secrets_file:
            Path(temp_secrets_file.name).unlink(missing_ok=True)

        _seeding_status["current_operation"] = "Completed" if not errors else "Failed"
        _seeding_status["progress"] = "2/2"

    except Exception as e:
        errors.append(f"Unexpected error: {str(e)}")
        _seeding_status["current_operation"] = "Failed"

    finally:
        # Reset status after a delay
        await asyncio.sleep(2)
        _seeding_status["is_running"] = False
        _seeding_status["current_operation"] = None
        _seeding_status["progress"] = None


@router.get("/available-apps", response_model=List[Dict[str, Any]])
async def get_available_apps() -> List[Dict[str, Any]]:
    """Get list of available apps from the apps directory"""
    try:
        apps_dir = Path("/workdir/apps")
        available_apps = []

        if apps_dir.exists():
            for app_dir in apps_dir.iterdir():
                if app_dir.is_dir():
                    app_json = app_dir / "app.json"
                    functions_json = app_dir / "functions.json"

                    if app_json.exists():
                        try:
                            with open(app_json) as f:
                                app_data = json.load(f)

                            app_info = {
                                "name": app_data.get("name", app_dir.name),
                                "display_name": app_data.get("display_name", app_data.get("name", app_dir.name)),
                                "description": app_data.get("description", ""),
                                "app_path": f"./apps/{app_dir.name}/app.json",
                                "functions_path": f"./apps/{app_dir.name}/functions.json" if functions_json.exists() else None,
                                "requires_secrets": _app_requires_secrets(app_data),
                                "auth_schemes": app_data.get("auth_schemes", [])
                            }
                            available_apps.append(app_info)
                        except Exception as e:
                            # Skip apps with invalid JSON
                            continue

        return available_apps

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get available apps: {str(e)}")


def _app_requires_secrets(app_data: Dict[str, Any]) -> bool:
    """Check if app requires OAuth2 secrets"""
    auth_schemes = app_data.get("auth_schemes", [])
    for scheme in auth_schemes:
        if isinstance(scheme, dict) and scheme.get("type") == "oauth2":
            return True
    return False


@router.get("/seeded-apps", response_model=List[Dict[str, Any]])
async def get_seeded_apps(
    db_session: Session = Depends(deps.yield_db_session),
) -> List[Dict[str, Any]]:
    """Get list of apps that are already seeded in the database"""
    try:
        apps = crud.apps.get_apps(db_session)
        seeded_apps = []

        for app in apps:
            app_info = {
                "id": str(app.id),
                "name": app.name,
                "display_name": app.display_name,
                "description": app.description,
                "category": app.category,
                "visibility_access": app.visibility_access,
                "created_at": app.created_at.isoformat() if app.created_at else None,
                "updated_at": app.updated_at.isoformat() if app.updated_at else None,
            }

            # Get function count for this app
            functions = crud.functions.get_functions_by_app_id(db_session, app.id)
            app_info["function_count"] = len(functions)

            seeded_apps.append(app_info)

        return seeded_apps

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get seeded apps: {str(e)}")