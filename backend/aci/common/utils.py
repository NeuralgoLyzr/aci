import json
import os
import re
import time
from functools import cache
from uuid import UUID

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aci.common.logging_setup import get_logger

logger = get_logger(__name__)


def check_and_get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Environment variable '{name}' is not set")
    if value == "":
        raise ValueError(f"Environment variable '{name}' is empty string")
    return value


def get_environment() -> str:
    """Get the current environment (AWS, AZURE, or AZURE/WTW)."""
    dev_env = os.getenv("DEV_ENV", "").upper()
    if dev_env in ("AZURE", "AZURE/WTW"):
        return dev_env
    return "AWS"


def is_azure_environment() -> bool:
    """Check if running in Azure environment (either AZURE or AZURE/WTW)."""
    return get_environment() in ("AZURE", "AZURE/WTW")


def is_wtw_environment() -> bool:
    """Check if running in WTW-specific Azure environment."""
    return get_environment() == "AZURE/WTW"


_db_url_cache: str | None = None
_db_token_cache: dict | None = None  # {"token": str, "expires_on": float} for Azure MI


def _get_azure_db_token_sync() -> str:
    """Get Azure PostgreSQL access token using Managed Identity (sync)."""
    global _db_token_cache

    # Check if we have a valid cached token (with 5-minute buffer)
    if _db_token_cache and time.time() < (_db_token_cache["expires_on"] - 300):
        return _db_token_cache["token"]

    try:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            # Use User-Assigned Managed Identity
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            # Fall back to DefaultAzureCredential
            credential = DefaultAzureCredential()

        # Get token for Azure PostgreSQL/MySQL
        token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        _db_token_cache = {"token": token.token, "expires_on": token.expires_on}
        logger.info(f"Azure DB token acquired (expires: {time.ctime(token.expires_on)})")
        return token.token

    except Exception as e:
        logger.error(f"Failed to acquire Azure DB token: {e}")
        raise RuntimeError(f"Failed to obtain Azure Database token: {e}") from e


async def _get_azure_db_token_async() -> str:
    """Get Azure PostgreSQL access token using Managed Identity (async)."""
    global _db_token_cache

    # Check if we have a valid cached token (with 5-minute buffer)
    if _db_token_cache and time.time() < (_db_token_cache["expires_on"] - 300):
        return _db_token_cache["token"]

    credential = None
    try:
        from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

        token = await credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        _db_token_cache = {"token": token.token, "expires_on": token.expires_on}
        logger.info(f"Azure DB token acquired (expires: {time.ctime(token.expires_on)})")
        return token.token

    except Exception as e:
        logger.error(f"Failed to acquire Azure DB token: {e}")
        raise RuntimeError(f"Failed to obtain Azure Database token: {e}") from e
    finally:
        if credential:
            await credential.close()


def _get_azure_keyvault_password_sync() -> str:
    """Fetch DB password from Azure Key Vault (sync)."""
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient

    keyvault_url = check_and_get_env_variable("AZURE_KEYVAULT_URL_FOR_DB")
    secret_name = check_and_get_env_variable("AZURE_DB_SECRET_NAME")

    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        credential = ManagedIdentityCredential(client_id=client_id)
    else:
        credential = DefaultAzureCredential()

    client = SecretClient(vault_url=keyvault_url, credential=credential)
    secret = client.get_secret(secret_name)
    secret_dict = json.loads(secret.value)
    return secret_dict["password"]


def _get_aws_password_sync() -> str:
    """Fetches the DB password from AWS Secrets Manager synchronously."""
    import boto3

    secret_name = check_and_get_env_variable("DB_SECRET_NAME")
    region_name = check_and_get_env_variable("AWS_REGION_NAME")

    client = boto3.client("secretsmanager", region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    secret_dict = json.loads(response["SecretString"])
    return secret_dict["password"]


async def _get_aws_password_async() -> str:
    """Fetches the DB password from AWS Secrets Manager asynchronously."""
    import aioboto3

    secret_name = check_and_get_env_variable("DB_SECRET_NAME")
    region_name = check_and_get_env_variable("AWS_REGION_NAME")

    async with aioboto3.Session(region_name=region_name).client("secretsmanager") as client:
        response = await client.get_secret_value(SecretId=secret_name)
        secret_dict = json.loads(response["SecretString"])
        return secret_dict["password"]


def get_db_password_sync() -> str:
    """
    Fetches the database credential based on environment.

    For AZURE:
    - If SERVER_USE_AZURE_MANAGED_IDENTITY=true: Uses Managed Identity token
    - If SERVER_DB_PASSWORD is set: Uses that password directly
    - Otherwise: Fetches from Azure Key Vault

    For AWS:
    - Fetches from AWS Secrets Manager
    """
    if is_azure_environment():
        use_mi = os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"
        if use_mi:
            return _get_azure_db_token_sync()

        # Check for direct password
        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # Fetch from Key Vault
        return _get_azure_keyvault_password_sync()
    else:
        return _get_aws_password_sync()


async def get_db_password() -> str:
    """
    Fetches the database credential based on environment (async).

    For AZURE:
    - If SERVER_USE_AZURE_MANAGED_IDENTITY=true: Uses Managed Identity token
    - If SERVER_DB_PASSWORD is set: Uses that password directly
    - Otherwise: Fetches from Azure Key Vault (sync fallback)

    For AWS:
    - Fetches from AWS Secrets Manager
    """
    if is_azure_environment():
        use_mi = os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"
        if use_mi:
            return await _get_azure_db_token_async()

        # Check for direct password
        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # Fetch from Key Vault (sync - azure SDK async support is limited)
        return _get_azure_keyvault_password_sync()
    else:
        return await _get_aws_password_async()


def construct_db_url_sync(
    scheme: str, user: str, host: str, port: str, db_name: str
) -> str:
    """
    Constructs the database URL synchronously.
    Fetches credential based on cloud provider (Azure or AWS).
    The result is cached to avoid repeated API calls.
    """
    global _db_url_cache
    if _db_url_cache is not None:
        return _db_url_cache

    password = get_db_password_sync()
    _db_url_cache = f"{scheme}://{user}:{password}@{host}:{port}/{db_name}"
    return _db_url_cache


async def construct_db_url(
    scheme: str, user: str, host: str, port: str, db_name: str
) -> str:
    """
    Constructs the database URL asynchronously.
    Fetches credential based on cloud provider (Azure or AWS).
    The result is cached to avoid repeated API calls.
    """
    global _db_url_cache
    if _db_url_cache is not None:
        return _db_url_cache

    password = await get_db_password()
    _db_url_cache = f"{scheme}://{user}:{password}@{host}:{port}/{db_name}"
    return _db_url_cache


def format_to_screaming_snake_case(name: str) -> str:
    """
    Convert a string with spaces, hyphens, slashes, camel case etc. to screaming snake case.
    e.g., "GitHub Create Repository" -> "GITHUB_CREATE_REPOSITORY"
    e.g., "GitHub/Create Repository" -> "GITHUB_CREATE_REPOSITORY"
    e.g., "github-create-repository" -> "GITHUB_CREATE_REPOSITORY"
    """
    name = re.sub(r"[\W]+", "_", name)  # Replace non-alphanumeric characters with underscore
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
    s3 = s2.replace("-", "_").replace("/", "_").replace(" ", "_")
    s3 = re.sub("_+", "_", s3)  # Replace multiple underscores with single underscore
    s4 = s3.upper().strip("_")

    return s4


# NOTE: it's important that you don't create a new engine for each session, which takes
# up db resources and will lead up to errors pretty fast
# TODO: fine tune the pool settings
@cache
def get_db_engine(db_url: str) -> Engine:
    return create_engine(
        db_url,
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,  # recycle connections after 1 hour
        pool_pre_ping=True,
    )


# NOTE: cache this because only one sessionmaker is needed for all db sessions
@cache
def get_sessionmaker(db_url: str) -> sessionmaker:
    engine = get_db_engine(db_url)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_db_session(db_url: str) -> Session:
    SessionMaker = get_sessionmaker(db_url)
    session: Session = SessionMaker()

    return session


def parse_app_name_from_function_name(function_name: str) -> str:
    """
    Parse the app name from a function name.
    e.g., "ACI_TEST__HELLO_WORLD" -> "ACI_TEST"
    """
    return function_name.split("__")[0]


def snake_to_camel(string: str) -> str:
    """
    Convert a snake case string to a camel case string.
    e.g., "snake_case_string" -> "SnakeCaseString"
    """
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def is_uuid(value: str | UUID) -> bool:
    if isinstance(value, UUID):
        return True
    try:
        UUID(value)
        return True
    except ValueError:
        return False


# WTW model name mappings
WTW_EMBEDDING_MODEL_MAP = {
    "text-embedding-3-small": "em3-small",
    "text-embedding-3-large": "em3-large",
    "text-embedding-ada-002": "ada",
}

WTW_LLM_MODEL_MAP = {
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4": "gpt-4",
    "gpt-35-turbo": "gpt-35-turbo",
}


def get_wtw_config() -> dict:
    """
    Get WTW-specific configuration from environment variables.

    Returns:
        Dictionary with wtw_api_base, wtw_api_version, wtw_api_scope
    """
    wtw_env = os.getenv("WTW_ENV", "DEV")
    if wtw_env == "PROD":
        wtw_api_base = os.getenv("WTW_API_BASE_PROD")
        wtw_api_scope = os.getenv("WTW_API_SCOPE_PROD")
    else:
        wtw_api_base = os.getenv("WTW_API_BASE_DEV")
        wtw_api_scope = os.getenv("WTW_API_SCOPE_DEV")

    wtw_api_version = os.getenv("WTW_API_VERSION", "2024-10-21")

    return {
        "wtw_api_base": wtw_api_base,
        "wtw_api_version": wtw_api_version,
        "wtw_api_scope": wtw_api_scope,
    }


def map_wtw_model_name(model_name: str, is_embedding: bool = False) -> str:
    """
    Map a standard model name to WTW deployment name.

    Args:
        model_name: Standard model name (e.g., "text-embedding-3-small")
        is_embedding: True if this is an embedding model

    Returns:
        WTW deployment name (e.g., "em3-small")
    """
    if is_embedding:
        return WTW_EMBEDDING_MODEL_MAP.get(model_name, model_name)
    return WTW_LLM_MODEL_MAP.get(model_name, model_name)


# Cache for WTW token
_wtw_token_cache: dict | None = None


def _get_wtw_token_sync() -> str:
    """Get WTW Azure OpenAI access token using Managed Identity (sync)."""
    global _wtw_token_cache

    # Check if we have a valid cached token (with 5-minute buffer)
    if _wtw_token_cache and time.time() < (_wtw_token_cache["expires_on"] - 300):
        return _wtw_token_cache["token"]

    try:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

        wtw_config = get_wtw_config()
        wtw_api_scope = wtw_config["wtw_api_scope"]

        if not wtw_api_scope:
            raise ValueError("WTW_API_SCOPE_DEV or WTW_API_SCOPE_PROD must be set for AZURE/WTW environment")

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

        token = credential.get_token(wtw_api_scope)
        _wtw_token_cache = {"token": token.token, "expires_on": token.expires_on}
        logger.info(f"WTW token acquired (expires: {time.ctime(token.expires_on)})")
        return token.token

    except Exception as e:
        logger.error(f"Failed to acquire WTW token: {e}")
        raise RuntimeError(f"Failed to obtain WTW token: {e}") from e


async def _get_wtw_token_async() -> str:
    """Get WTW Azure OpenAI access token using Managed Identity (async)."""
    global _wtw_token_cache

    # Check if we have a valid cached token (with 5-minute buffer)
    if _wtw_token_cache and time.time() < (_wtw_token_cache["expires_on"] - 300):
        return _wtw_token_cache["token"]

    credential = None
    try:
        from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential

        wtw_config = get_wtw_config()
        wtw_api_scope = wtw_config["wtw_api_scope"]

        if not wtw_api_scope:
            raise ValueError("WTW_API_SCOPE_DEV or WTW_API_SCOPE_PROD must be set for AZURE/WTW environment")

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

        token = await credential.get_token(wtw_api_scope)
        _wtw_token_cache = {"token": token.token, "expires_on": token.expires_on}
        logger.info(f"WTW token acquired (expires: {time.ctime(token.expires_on)})")
        return token.token

    except Exception as e:
        logger.error(f"Failed to acquire WTW token: {e}")
        raise RuntimeError(f"Failed to obtain WTW token: {e}") from e
    finally:
        if credential:
            await credential.close()


def get_openai_client(
    api_key: str | None = None,
    azure_endpoint: str | None = None,
    azure_api_version: str | None = None,
):
    """
    Factory function to create the appropriate OpenAI client based on environment.

    For AZURE/WTW environment:
        - Returns AzureOpenAI client configured for WTW
        - Uses WTW_API_BASE_DEV/PROD as endpoint
        - Uses WTW_API_SCOPE for Managed Identity token

    For AZURE environment:
        - Returns AzureOpenAI client
        - Uses provided azure_endpoint and azure_api_version
        - api_key can be None if using Managed Identity

    For AWS environment:
        - Returns standard OpenAI client
        - Requires api_key

    Args:
        api_key: OpenAI API key (required for AWS, optional for Azure with MI)
        azure_endpoint: Azure OpenAI endpoint URL (required for AZURE, ignored for WTW)
        azure_api_version: Azure OpenAI API version (defaults to "2024-02-01" for AZURE, "2024-10-21" for WTW)

    Returns:
        OpenAI or AzureOpenAI client instance
    """
    from openai import AzureOpenAI, OpenAI

    if is_wtw_environment():
        # AZURE/WTW - use WTW-specific configuration
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider

        wtw_config = get_wtw_config()
        wtw_api_base = wtw_config["wtw_api_base"]
        wtw_api_version = wtw_config["wtw_api_version"]
        wtw_api_scope = wtw_config["wtw_api_scope"]

        if not wtw_api_base:
            raise ValueError("WTW_API_BASE_DEV or WTW_API_BASE_PROD must be set for AZURE/WTW environment")
        if not wtw_api_scope:
            raise ValueError("WTW_API_SCOPE_DEV or WTW_API_SCOPE_PROD must be set for AZURE/WTW environment")

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

        token_provider = get_bearer_token_provider(credential, wtw_api_scope)

        return AzureOpenAI(
            azure_ad_token_provider=token_provider,
            api_version=wtw_api_version,
            azure_endpoint=wtw_api_base,
        )

    elif is_azure_environment():
        # Standard Azure OpenAI
        if not azure_endpoint:
            raise ValueError("azure_endpoint is required for Azure environment")

        azure_api_version = azure_api_version or "2024-02-01"

        if api_key:
            # Use API key authentication
            return AzureOpenAI(
                api_key=api_key,
                api_version=azure_api_version,
                azure_endpoint=azure_endpoint,
            )
        else:
            # Use Azure AD / Managed Identity authentication
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider

            client_id = os.getenv("AZURE_CLIENT_ID")
            if client_id:
                credential = ManagedIdentityCredential(client_id=client_id)
            else:
                credential = DefaultAzureCredential()

            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )

            return AzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=azure_api_version,
                azure_endpoint=azure_endpoint,
            )
    else:
        # AWS / Standard OpenAI
        if not api_key:
            raise ValueError("api_key is required for AWS/standard OpenAI environment")
        return OpenAI(api_key=api_key)
