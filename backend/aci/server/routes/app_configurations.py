from typing import Annotated

from fastapi import APIRouter, Depends, Query

from aci.common.db import crud
from aci.common.db.sql_models import AppConfiguration
from aci.common.enums import Visibility
from aci.common.exceptions import (
    AppConfigurationAlreadyExists,
    AppConfigurationNotFound,
    AppNotFound,
    AppSecuritySchemeNotSupported,
)
from aci.common.logging_setup import get_logger
from aci.common.schemas.app_configurations import (
    AppConfigurationCreate,
    AppConfigurationCreateByAppId,
    AppConfigurationPublic,
    AppConfigurationsList,
    AppConfigurationUpdate,
)
from aci.server import config
from aci.server import dependencies as deps
from uuid import UUID

router = APIRouter()
logger = get_logger(__name__)


# TODO: when creating an app configuration, allow user to specify list of agents that are allowed to access the app
@router.post("", response_model=AppConfigurationPublic, response_model_exclude_none=True)
async def create_app_configuration(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: AppConfigurationCreate,
) -> AppConfiguration:
    """Create an app configuration for a project"""

    # TODO: validate security scheme
    app = crud.apps.get_app(
        context.db_session,
        body.app_name,
        context.project.visibility_access == Visibility.PUBLIC,
        True,
        context.api_key_id,
    )
    if not app:
        logger.error(f"App not found, app_name={body.app_name}")
        raise AppNotFound(f"app={body.app_name} not found")

    if crud.app_configurations.app_configuration_exists(
        context.db_session, context.project.id, body.app_name
    ):
        logger.error(f"App configuration already exists, app_name={body.app_name}")
        raise AppConfigurationAlreadyExists(
            f"app={body.app_name} already configured for project={context.project.id}"
        )

    if app.security_schemes.get(body.security_scheme) is None:
        logger.error(
            f"App does not support specified security scheme, app_name={body.app_name}, "
            f"security_scheme={body.security_scheme}"
        )
        raise AppSecuritySchemeNotSupported(
            f"app={body.app_name} does not support security_scheme={body.security_scheme}"
        )
    app_configuration = crud.app_configurations.create_app_configuration(
        context.db_session,
        context.project.id,
        body,
        context.api_key_id,
    )
    context.db_session.commit()

    return app_configuration


@router.post("/by-app-id", response_model=AppConfigurationPublic, response_model_exclude_none=True)
async def create_app_configuration_by_app_id(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    body: AppConfigurationCreateByAppId,
) -> AppConfiguration:
    """Create an app configuration for a project using app_id"""

    # Get the app by ID to verify it exists
    app = crud.apps.get_app_by_id(context.db_session, body.app_id)
    if not app:
        logger.error(f"App not found, app_id={body.app_id}")
        raise AppNotFound(f"app with id={body.app_id} not found")

    # Check if app configuration already exists
    if crud.app_configurations.app_configuration_exists_by_app_id(
        context.db_session, context.project.id, body.app_id
    ):
        logger.error(f"App configuration already exists, app_id={body.app_id}")
        raise AppConfigurationAlreadyExists(
            f"app with id={body.app_id} already configured for project={context.project.id}"
        )

    # Validate that the app supports the specified security scheme
    if app.security_schemes.get(body.security_scheme) is None:
        logger.error(
            f"App does not support specified security scheme, app_id={body.app_id}, "
            f"security_scheme={body.security_scheme}"
        )
        raise AppSecuritySchemeNotSupported(
            f"app with id={body.app_id} does not support security_scheme={body.security_scheme}"
        )

    # Create a temporary AppConfigurationCreate object for the CRUD function
    # The CRUD function expects AppConfigurationCreate, but we only use the fields that don't include app_name
    temp_create_schema = AppConfigurationCreate(
        app_name=app.name,  # This won't be used in the by_app_id CRUD function
        security_scheme=body.security_scheme,
        security_scheme_overrides=body.security_scheme_overrides,
        all_functions_enabled=body.all_functions_enabled,
        enabled_functions=body.enabled_functions,
    )

    app_configuration = crud.app_configurations.create_app_configuration_by_app_id(
        context.db_session,
        context.project.id,
        body.app_id,
        temp_create_schema,
    )
    context.db_session.commit()

    return app_configuration


@router.delete("/by-app-id/{app_id}")
async def delete_app_configuration_by_app_id(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    app_id: UUID,
) -> None:
    """
    Delete an app configuration by app_id
    Warning: This will delete the app configuration from the project,
    associated linked accounts, and remove the app from agents' allowed_apps.
    """

    app_configuration = crud.app_configurations.get_app_configuration_by_app_id(
        context.db_session, context.project.id, app_id
    )
    if not app_configuration:
        logger.error(f"App configuration not found, app_id={app_id}")
        raise AppConfigurationNotFound(
            f"Configuration for app_id={app_id} not found, please configure the app first"
        )

    # TODO: double check atomic operations like below in other api endpoints
    # 1. Delete all linked accounts for this app configuration
    number_of_linked_accounts_deleted = crud.linked_accounts.delete_linked_accounts_by_app_id(
        context.db_session, context.project.id, app_id
    )
    logger.warning(
        f"Deleted linked accounts, number_of_linked_accounts_deleted={number_of_linked_accounts_deleted}, "
        f"app_id={app_id}"
    )
    # 2. Delete the app configuration record
    crud.app_configurations.delete_app_configuration_by_app_id(
        context.db_session, context.project.id, app_id
    )

    # 3. Delete this App from all agents' allowed_apps if exists
    crud.projects.delete_app_from_agents_allowed_apps_by_app_id(
        context.db_session, context.project.id, app_id
    )

    context.db_session.commit()


@router.get("", response_model=list[AppConfigurationPublic], response_model_exclude_none=True)
async def list_app_configurations(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    query_params: Annotated[AppConfigurationsList, Query()],
) -> list[AppConfiguration]:
    """List all app configurations for a project, with optionally filters"""

    return crud.app_configurations.get_app_configurations(
        context.db_session,
        context.project.id,
        query_params.app_names,
        query_params.limit,
        query_params.offset,
    )


@router.get("/{app_name}", response_model=AppConfigurationPublic, response_model_exclude_none=True)
async def get_app_configuration(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    app_name: str,
) -> AppConfiguration:
    """Get an app configuration by app name"""

    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, app_name
    )
    if not app_configuration:
        logger.error(f"App configuration not found, app_name={app_name}")
        raise AppConfigurationNotFound(
            f"Configuration for app={app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{app_name}"
        )
    return app_configuration


@router.delete("/{app_name}")
async def delete_app_configuration(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    app_name: str,
) -> None:
    """
    Delete an app configuration by app name
    Warning: This will delete the app configuration from the project,
    associated linked accounts, and then the app configuration record itself.
    """

    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, app_name
    )
    if not app_configuration:
        logger.error(f"App configuration not found, app_name={app_name}")
        raise AppConfigurationNotFound(
            f"Configuration for app={app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{app_name}"
        )

    # TODO: double check atomic operations like below in other api endpoints
    # 1. Delete all linked accounts for this app configuration
    number_of_linked_accounts_deleted = crud.linked_accounts.delete_linked_accounts(
        context.db_session, context.project.id, app_name
    )
    logger.warning(
        f"Deleted linked accounts, number_of_linked_accounts_deleted={number_of_linked_accounts_deleted}, "
        f"app_name={app_name}"
    )
    # 2. Delete the app configuration record
    crud.app_configurations.delete_app_configuration(
        context.db_session, context.project.id, app_name
    )

    # 3. delete this App from all agents' allowed_apps if exists
    crud.projects.delete_app_from_agents_allowed_apps(
        context.db_session, context.project.id, app_name
    )

    context.db_session.commit()


@router.patch(
    "/{app_name}", response_model=AppConfigurationPublic, response_model_exclude_none=True
)
async def update_app_configuration(
    context: Annotated[deps.RequestContext, Depends(deps.get_request_context)],
    app_name: str,
    body: AppConfigurationUpdate,
) -> AppConfiguration:
    """
    Update an app configuration by app name.
    If a field is not included in the request body, it will not be changed.
    """
    # validations
    app_configuration = crud.app_configurations.get_app_configuration(
        context.db_session, context.project.id, app_name
    )
    if not app_configuration:
        logger.error(f"App configuration not found, app_name={app_name}")
        raise AppConfigurationNotFound(
            f"Configuration for app={app_name} not found, please configure the app first {config.DEV_PORTAL_URL}/apps/{app_name}"
        )

    crud.app_configurations.update_app_configuration(context.db_session, app_configuration, body)
    context.db_session.commit()

    return app_configuration
