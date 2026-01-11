import json
import os
import re
from datetime import datetime, timedelta
from functools import cache
from uuid import UUID

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
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


_db_url_cache: str | None = None
_db_token_cache: tuple[str, datetime] | None = None  # (token, expiry_time) - used for both local caching


def get_db_password_sync() -> str:
    """
    Fetches the database authentication credential (password or token) synchronously.

    Behavior depends on configuration:
    - If SERVER_USE_AZURE_MANAGED_IDENTITY=true: Fetches Azure Database token via Managed Identity
    - Else: Fetches password from environment or Azure Key Vault

    Tokens are cached and auto-refreshed 5 minutes before expiry.
    """
    global _db_token_cache

    use_managed_identity = os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"

    if use_managed_identity:
        # Return cached token if still valid (refresh 5 minutes before expiry)
        if _db_token_cache is not None:
            token, expiry_time = _db_token_cache
            if datetime.utcnow() < (expiry_time - timedelta(minutes=5)):
                return token

        try:
            # Get token for Azure Database (works for PostgreSQL, MySQL, MariaDB, etc.)
            credential = DefaultAzureCredential()
            token_credential = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

            # Cache token with expiry time (Azure tokens are typically valid for 1 hour)
            expiry_time = datetime.utcnow() + timedelta(hours=1)
            _db_token_cache = (token_credential.token, expiry_time)

            return token_credential.token
        except Exception as e:
            raise RuntimeError(
                f"Failed to obtain Azure Database token using Managed Identity: {e}. "
                "Ensure the application has appropriate Azure RBAC permissions for database access."
            ) from e
    else:
        # Password-based authentication (local dev or Key Vault)
        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # For production, fetch from Azure Key Vault
        try:
            keyvault_url = check_and_get_env_variable("AZURE_KEYVAULT_URL_FOR_DB")
            secret_name = check_and_get_env_variable("AZURE_DB_SECRET_NAME")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(secret_name)
            secret_dict = json.loads(secret.value)
            return secret_dict["password"]
        except ValueError as e:
            raise RuntimeError(
                "Database password not found. Either set SERVER_DB_PASSWORD "
                "for local development, or configure AZURE_KEYVAULT_URL_FOR_DB and AZURE_DB_SECRET_NAME "
                "for production."
            ) from e


async def get_db_password() -> str:
    """
    Fetches the database authentication credential (password or token) asynchronously.

    Behavior depends on configuration:
    - If SERVER_USE_AZURE_MANAGED_IDENTITY=true: Fetches Azure Database token via Managed Identity
    - Else: Fetches password from environment or Azure Key Vault

    Tokens are cached and auto-refreshed 5 minutes before expiry.
    """
    global _db_token_cache

    use_managed_identity = os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"

    if use_managed_identity:
        # Return cached token if still valid (refresh 5 minutes before expiry)
        if _db_token_cache is not None:
            token, expiry_time = _db_token_cache
            if datetime.utcnow() < (expiry_time - timedelta(minutes=5)):
                return token

        try:
            # Get token for Azure Database (works for PostgreSQL, MySQL, MariaDB, etc.)
            credential = DefaultAzureCredential()
            token_credential = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

            # Cache token with expiry time (Azure tokens are typically valid for 1 hour)
            expiry_time = datetime.utcnow() + timedelta(hours=1)
            _db_token_cache = (token_credential.token, expiry_time)

            return token_credential.token
        except Exception as e:
            raise RuntimeError(
                f"Failed to obtain Azure Database token using Managed Identity: {e}. "
                "Ensure the application has appropriate Azure RBAC permissions for database access."
            ) from e
    else:
        # Password-based authentication (local dev or Key Vault)
        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # For production, fetch from Azure Key Vault
        try:
            keyvault_url = check_and_get_env_variable("AZURE_KEYVAULT_URL_FOR_DB")
            secret_name = check_and_get_env_variable("AZURE_DB_SECRET_NAME")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(secret_name)
            secret_dict = json.loads(secret.value)
            return secret_dict["password"]
        except ValueError as e:
            raise RuntimeError(
                "Database password not found. Either set SERVER_DB_PASSWORD "
                "for local development, or configure AZURE_KEYVAULT_URL_FOR_DB and AZURE_DB_SECRET_NAME "
                "for production."
            ) from e


def construct_db_url_sync(
    scheme: str, user: str, host: str, port: str, db_name: str
) -> str:
    """
    Constructs the database URL synchronously.

    Fetches authentication credential (password or Azure Managed Identity token) based on configuration.
    The result is cached to avoid repeated API calls.

    Supports:
    - Local password-based auth (SERVER_DB_PASSWORD)
    - Azure Key Vault password storage
    - Azure Managed Identity tokens (if SERVER_USE_AZURE_MANAGED_IDENTITY=true)
    """
    global _db_url_cache
    if _db_url_cache is not None:
        return _db_url_cache

    credential = get_db_password_sync()
    _db_url_cache = f"{scheme}://{user}:{credential}@{host}:{port}/{db_name}"
    return _db_url_cache


async def construct_db_url(
    scheme: str, user: str, host: str, port: str, db_name: str
) -> str:
    """
    Constructs the database URL asynchronously.

    Fetches authentication credential (password or Azure Managed Identity token) based on configuration.
    The result is cached to avoid repeated API calls.

    Supports:
    - Local password-based auth (SERVER_DB_PASSWORD)
    - Azure Key Vault password storage
    - Azure Managed Identity tokens (if SERVER_USE_AZURE_MANAGED_IDENTITY=true)
    """
    global _db_url_cache
    if _db_url_cache is not None:
        return _db_url_cache

    credential = await get_db_password()
    _db_url_cache = f"{scheme}://{user}:{credential}@{host}:{port}/{db_name}"
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
