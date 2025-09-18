"""
Seeding information endpoint to get API keys and project info after seeding
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aci.server import dependencies as deps
from aci.common.db import crud

router = APIRouter()


@router.get("/seeding-info", response_model=Dict[str, Any])
async def get_seeding_info(
    db_session: Session = Depends(deps.yield_db_session),
) -> Dict[str, Any]:
    """
    Get seeding information including API keys and project IDs
    Useful for getting test credentials after auto-seeding
    """
    try:
        # Get all projects
        projects = crud.projects.get_projects(db_session)
        
        seeding_info = {
            "total_projects": len(projects),
            "total_apps": len(crud.apps.get_apps(db_session)),
            "total_functions": len(crud.functions.get_functions(db_session)),
            "projects": []
        }
        
        for project in projects:
            # Get agents for this project
            agents = crud.agents.get_agents_by_project_id(db_session, project.id)
            
            project_info = {
                "project_id": str(project.id),
                "project_name": project.name,
                "owner_id": str(project.owner_id),
                "agents": []
            }
            
            for agent in agents:
                # Get API key for this agent
                api_key = crud.projects.get_api_key_by_agent_id(db_session, agent.id)
                
                agent_info = {
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "agent_description": agent.description,
                    "api_key": str(api_key.key) if api_key else None
                }
                
                project_info["agents"].append(agent_info)
            
            seeding_info["projects"].append(project_info)
        
        return seeding_info
        
    except Exception as e:
        return {
            "error": f"Failed to get seeding info: {str(e)}",
            "total_projects": 0,
            "total_apps": 0,
            "total_functions": 0,
            "projects": []
        }
