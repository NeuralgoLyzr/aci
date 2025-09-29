"""
Tool seeding routes for managing apps and functions via API
Matches the Docker exec commands from README.md
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aci.cli.commands import upsert_app, upsert_functions
from aci.common.db import crud
from aci.common.db.sql_models import App, Function
from aci.common.enums import Visibility
from aci.common.logging_setup import get_logger
from aci.common.schemas.app import AppDetails
from aci.common.schemas.function import FunctionDetails
from aci.server import config
from aci.server import dependencies as deps

logger = get_logger(__name__)
router = APIRouter()


class AppUpsertRequest(BaseModel):
    """Request model for upserting an app - matches CLI command"""
    app_path: str  # Path to app.json file (e.g., "./apps/gmail/app.json")
    secrets_path: Optional[str] = None  # Path to secrets file (e.g., "./apps/gmail/.app.secrets.json")
    secrets: Optional[Dict[str, str]] = None  # JSON secrets object for OAuth2 credentials
    skip_dry_run: bool = True


class FunctionsUpsertRequest(BaseModel):
    """Request model for upserting functions - matches CLI command"""
    functions_path: str  # Path to functions.json file (e.g., "./apps/gmail/functions.json")
    skip_dry_run: bool = True


class SeedingRequest(BaseModel):
    """Request model for seeding tools - matches frontend interface"""
    app_path: str
    functions_path: Optional[str] = None
    secrets: Optional[Dict[str, str]] = None
    skip_dry_run: bool = True


class ToolSeedingResponse(BaseModel):
    """Response model for tool seeding operations"""
    success: bool
    message: str
    app_id: Optional[UUID] = None
    function_names: Optional[List[str]] = None


@router.post("/upsert-app", response_model=ToolSeedingResponse)
async def upsert_app_via_api(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    request: AppUpsertRequest,
) -> ToolSeedingResponse:
    """
    Upsert an app via API, equivalent to:
    docker compose exec runner python -m aci.cli upsert-app --app-file ./apps/gmail/app.json --secrets-file ./apps/gmail/.app.secrets.json
    
    This allows adding new tools/apps with their JSON configurations and credentials.
    """
    try:
        # Convert relative path to absolute path
        app_file_path = Path(request.app_path)
        if not app_file_path.is_absolute():
            # Assume it's relative to the backend directory
            app_file_path = Path("/workdir") / app_file_path
        
        if not app_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"App file not found at path: {app_file_path}"
            )
        
        # Handle secrets - either from file or from request
        secrets_file_path = None
        if request.secrets_path:
            secrets_file_path = Path(request.secrets_path)
            if not secrets_file_path.is_absolute():
                secrets_file_path = Path("/workdir") / secrets_file_path
                
            if not secrets_file_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Secrets file not found at path: {secrets_file_path}"
                )
        elif request.secrets:
            # Create temporary secrets file from request data
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(request.secrets, f)
                secrets_file_path = Path(f.name)
        
        # Use the CLI helper function
        app_id = upsert_app.upsert_app_helper(
            db_session=context.db_session,
            app_file=app_file_path,
            secrets_file=secrets_file_path,
            skip_dry_run=request.skip_dry_run
        )
        
        # Clean up temporary secrets file if created
        if request.secrets and secrets_file_path and secrets_file_path.exists():
            secrets_file_path.unlink()
        
        return ToolSeedingResponse(
            success=True,
            message=f"Successfully upserted app from path '{request.app_path}'",
            app_id=app_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upserting app from path {request.app_path}: {str(e)}")
        return ToolSeedingResponse(
            success=False,
            message=f"Failed to upsert app from path '{request.app_path}': {str(e)}"
        )


@router.post("/upsert-functions", response_model=ToolSeedingResponse)
async def upsert_functions_via_api(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    request: FunctionsUpsertRequest,
) -> ToolSeedingResponse:
    """
    Upsert functions via API, equivalent to:
    docker compose exec runner python -m aci.cli upsert-functions --functions-file ./apps/gmail/functions.json
    
    This allows adding new functions for existing apps.
    """
    try:
        # Convert relative path to absolute path
        functions_file_path = Path(request.functions_path)
        if not functions_file_path.is_absolute():
            # Assume it's relative to the backend directory
            functions_file_path = Path("/workdir") / functions_file_path
        
        if not functions_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Functions file not found at path: {functions_file_path}"
            )
        
        # Use the CLI helper function
        function_names = upsert_functions.upsert_functions_helper(
            functions_file=functions_file_path,
            skip_dry_run=request.skip_dry_run
        )
        
        return ToolSeedingResponse(
            success=True,
            message=f"Successfully upserted {len(function_names)} functions from path '{request.functions_path}'",
            function_names=function_names
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upserting functions from path {request.functions_path}: {str(e)}")
        return ToolSeedingResponse(
            success=False,
            message=f"Failed to upsert functions from path '{request.functions_path}': {str(e)}"
        )


@router.post("/seed-tool", response_model=ToolSeedingResponse)
async def seed_tool(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    request: SeedingRequest,
) -> ToolSeedingResponse:
    """
    Seed a tool (app + functions) via API - matches frontend interface.
    This is the main endpoint that the frontend tool-seeding page uses.
    """
    try:
        results = []
        
        # 1. Upsert the app first
        app_request = AppUpsertRequest(
            app_path=request.app_path,
            secrets=request.secrets,
            skip_dry_run=request.skip_dry_run
        )
        
        app_response = await upsert_app_via_api(context, app_request)
        results.append(f"App: {app_response.message}")
        
        if not app_response.success:
            return ToolSeedingResponse(
                success=False,
                message=f"Failed to seed tool - App upsert failed: {app_response.message}"
            )
        
        # 2. Upsert functions if functions_path is provided
        if request.functions_path:
            functions_request = FunctionsUpsertRequest(
                functions_path=request.functions_path,
                skip_dry_run=request.skip_dry_run
            )
            
            functions_response = await upsert_functions_via_api(context, functions_request)
            results.append(f"Functions: {functions_response.message}")
            
            if not functions_response.success:
                return ToolSeedingResponse(
                    success=False,
                    message=f"Partially failed to seed tool - Functions upsert failed: {functions_response.message}"
                )
        
        return ToolSeedingResponse(
            success=True,
            message=f"Successfully seeded tool. {' | '.join(results)}",
            app_id=app_response.app_id,
            function_names=functions_response.function_names if request.functions_path else None
        )
        
    except Exception as e:
        logger.error(f"Error seeding tool: {str(e)}")
        return ToolSeedingResponse(
            success=False,
            message=f"Failed to seed tool: {str(e)}"
        )


@router.get("/available-apps", response_model=List[Dict[str, Any]])
async def get_available_apps(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
) -> List[Dict[str, Any]]:
    """
    Get list of available apps that can be seeded.
    This scans the apps directory for available app configurations.
    """
    try:
        # Scan the apps directory for available apps
        apps_dir = Path("/workdir/apps")
        available_apps = []
        
        if apps_dir.exists():
            for app_dir in apps_dir.iterdir():
                if app_dir.is_dir():
                    app_json_path = app_dir / "app.json"
                    functions_json_path = app_dir / "functions.json"
                    secrets_json_path = app_dir / ".app.secrets.json"
                    
                    if app_json_path.exists():
                        try:
                            # Read app.json to get app details
                            with open(app_json_path) as f:
                                app_data = json.load(f)
                            
                            available_apps.append({
                                "name": app_data.get("name", app_dir.name),
                                "display_name": app_data.get("display_name", app_data.get("name", app_dir.name)),
                                "description": app_data.get("description", ""),
                                "app_path": f"./apps/{app_dir.name}/app.json",
                                "functions_path": f"./apps/{app_dir.name}/functions.json" if functions_json_path.exists() else None,
                                "requires_secrets": secrets_json_path.exists() or "oauth2" in app_data.get("security_schemes", {}),
                                "security_schemes": list(app_data.get("security_schemes", {}).keys())
                            })
                        except Exception as e:
                            logger.warning(f"Could not read app.json for {app_dir.name}: {e}")
                            continue
        
        return available_apps
        
    except Exception as e:
        logger.error(f"Error getting available apps: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available apps: {str(e)}"
        )


@router.get("/seeded-apps", response_model=List[AppDetails])
async def get_seeded_apps(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
) -> List[AppDetails]:
    """
    Get list of apps that have been seeded (exist in the database).
    """
    try:
        # Get all apps from the database
        apps = crud.apps.get_apps(
            context.db_session,
            public_only=False,  # Include all apps for admin purposes
            active_only=False,  # Include inactive apps
            app_names=None,
            limit=None,
            offset=0
        )
        
        # Convert to AppDetails format
        app_details = []
        for app in apps:
            app_detail = AppDetails(
                id=app.id,
                name=app.name,
                display_name=app.display_name,
                provider=app.provider,
                version=app.version,
                description=app.description,
                logo=app.logo,
                categories=app.categories,
                visibility=app.visibility,
                active=app.active,
                security_schemes=list(app.security_schemes.keys()),
                supported_security_schemes=app.security_schemes,
                functions=[FunctionDetails.model_validate(func) for func in app.functions],
                created_at=app.created_at,
                updated_at=app.updated_at,
            )
            app_details.append(app_detail)
        
        return app_details
        
    except Exception as e:
        logger.error(f"Error getting seeded apps: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get seeded apps: {str(e)}"
        )


@router.get("/seeding-status", response_model=Dict[str, Any])
async def get_seeding_status(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
) -> Dict[str, Any]:
    """
    Get the current seeding status.
    This is used by the frontend to show seeding progress.
    """
    try:
        # For now, return a simple status
        # You can enhance this to track actual seeding operations
        return {
            "is_seeded": True,
            "is_running": False,
            "last_seeded_at": None,
            "seeding_version": "1.0",
            "environment": "development"
        }
        
    except Exception as e:
        logger.error(f"Error getting seeding status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get seeding status: {str(e)}"
        )


@router.post("/run-seed-script", response_model=ToolSeedingResponse)
async def run_seed_script(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    script_path: str = "./scripts/seed_db.sh",
    args: List[str] = None,
) -> ToolSeedingResponse:
    """
    Run a seeding script via API, equivalent to:
    docker compose exec runner ./scripts/seed_db.sh --all --mock
    
    This allows running the full database seeding process.
    """
    try:
        if args is None:
            args = []
        
        # Convert relative path to absolute path
        script_file_path = Path(script_path)
        if not script_file_path.is_absolute():
            script_file_path = Path("/workdir") / script_file_path
        
        if not script_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Script file not found at path: {script_file_path}"
            )
        
        # Make script executable
        script_file_path.chmod(0o755)
        
        # Run the script
        cmd = [str(script_file_path)] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd="/workdir"
        )
        
        if result.returncode == 0:
            return ToolSeedingResponse(
                success=True,
                message=f"Successfully ran seeding script: {result.stdout}",
            )
        else:
            return ToolSeedingResponse(
                success=False,
                message=f"Seeding script failed: {result.stderr}",
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running seeding script {script_path}: {str(e)}")
        return ToolSeedingResponse(
            success=False,
            message=f"Failed to run seeding script '{script_path}': {str(e)}"
        )