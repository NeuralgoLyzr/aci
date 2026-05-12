import json
import os
import re
import time
from functools import cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, event
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
    """Get the current cloud environment (AWS, AZURE, or AZURE/WTW)."""
    cloud_env = os.getenv("CLOUD_ENVIRONMENT", "").upper()
    if cloud_env in ("AZURE", "AZURE/WTW"):
        return cloud_env
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
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

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

        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

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

        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        return _get_azure_keyvault_password_sync()
    else:
        return await _get_aws_password_async()


def construct_db_url_sync(
    scheme: str, user: str, host: str, port: str, db_name: str
) -> str:
    """
    Constructs the database URL by fetching the password based on environment.
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
    Constructs the database URL by fetching the password based on environment.
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
    engine = create_engine(
        db_url,
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,  # recycle connections after 30 min (before Azure MI token expires)
        pool_pre_ping=True,
    )

    # For Azure Managed Identity: refresh the token on each new physical connection
    if is_azure_environment() and os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true":
        @event.listens_for(engine, "do_connect")
        def _refresh_azure_token(dialect, conn_rec, cargs, cparams):  # type: ignore
            cparams["password"] = _get_azure_db_token_sync()

    return engine


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


def get_wtw_config() -> dict:
    """Get WTW-specific configuration from environment variables."""
    return {
        "wtw_api_base": check_and_get_env_variable("WTW_API_BASE"),
        "wtw_api_version": os.getenv("WTW_API_VERSION", "2024-02-01"),
        "wtw_api_scope": check_and_get_env_variable("WTW_API_SCOPE"),
    }


def map_wtw_model_name(model_name: str, is_embedding: bool = False) -> str:
    """Map standard model names to WTW deployment names."""
    wtw_model_map = {
        "text-embedding-3-small": "em3-small",
        "text-embedding-3-large": "em3-large",
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
    }
    mapped = wtw_model_map.get(model_name, model_name)
    logger.debug(f"WTW model mapping: {model_name} -> {mapped}")
    return mapped


def get_openai_client(
    api_key: str | None = None,
    azure_endpoint: str | None = None,
    azure_api_version: str | None = None,
):
    """
    Create an OpenAI client based on the environment.
    Returns AzureOpenAI for Azure environments, standard OpenAI for AWS.
    """
    if is_wtw_environment():
        from openai import AzureOpenAI

        wtw_config = get_wtw_config()
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider

        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            credential = ManagedIdentityCredential(client_id=client_id)
        else:
            credential = DefaultAzureCredential()

        token_provider = get_bearer_token_provider(credential, wtw_config["wtw_api_scope"])

        return AzureOpenAI(
            azure_endpoint=wtw_config["wtw_api_base"],
            api_version=wtw_config["wtw_api_version"],
            azure_ad_token_provider=token_provider,
        )
    elif is_azure_environment():
        from openai import AzureOpenAI

        kwargs: dict = {
            "azure_endpoint": azure_endpoint,
            "api_version": azure_api_version or "2024-02-01",
        }
        if api_key:
            kwargs["api_key"] = api_key
        else:
            # Use Managed Identity
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider

            client_id = os.getenv("AZURE_CLIENT_ID")
            if client_id:
                credential = ManagedIdentityCredential(client_id=client_id)
            else:
                credential = DefaultAzureCredential()

            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            kwargs["azure_ad_token_provider"] = token_provider

        return AzureOpenAI(**kwargs)
    else:
        from openai import OpenAI

        return OpenAI(api_key=api_key)
