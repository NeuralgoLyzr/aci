import json
import os
import time
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from aci.common.db.sql_models import Base

load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Cache for Azure DB token
_db_token_cache: dict | None = None


def _check_and_get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Environment variable '{name}' is not set")
    if value == "":
        raise ValueError(f"Environment variable '{name}' is empty string")
    return value


def _get_environment() -> str:
    """Get the current environment (AWS, AZURE, or AZURE/WTW)."""
    dev_env = os.getenv("DEV_ENV", "").upper()
    if dev_env in ("AZURE", "AZURE/WTW"):
        return dev_env
    return "AWS"


def _is_azure_environment() -> bool:
    """Check if running in Azure environment."""
    return _get_environment() in ("AZURE", "AZURE/WTW")


def _get_azure_db_token() -> str:
    """Get Azure PostgreSQL access token using Managed Identity."""
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

        # Get token for Azure PostgreSQL
        token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        _db_token_cache = {"token": token.token, "expires_on": token.expires_on}
        return token.token

    except Exception as e:
        raise RuntimeError(f"Failed to obtain Azure Database token: {e}") from e


def _get_azure_keyvault_password() -> str:
    """Fetch DB password from Azure Key Vault."""
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient

    keyvault_url = _check_and_get_env_variable("AZURE_KEYVAULT_URL_FOR_DB")
    secret_name = _check_and_get_env_variable("AZURE_DB_SECRET_NAME")

    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        credential = ManagedIdentityCredential(client_id=client_id)
    else:
        credential = DefaultAzureCredential()

    client = SecretClient(vault_url=keyvault_url, credential=credential)
    secret = client.get_secret(secret_name)
    secret_dict = json.loads(secret.value)
    return secret_dict["password"]


def _get_aws_db_password() -> str:
    """Fetches the DB password from AWS Secrets Manager synchronously."""
    import boto3

    secret_name = _check_and_get_env_variable("DB_SECRET_NAME")
    region_name = _check_and_get_env_variable("AWS_REGION_NAME")

    client = boto3.client("secretsmanager", region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    secret_dict = json.loads(response["SecretString"])
    return secret_dict["password"]


def _get_db_password() -> str:
    """
    Fetches the database credential based on environment.

    For AZURE/AZURE/WTW:
    - If SERVER_USE_AZURE_MANAGED_IDENTITY=true: Uses Managed Identity token
    - If SERVER_DB_PASSWORD is set: Uses that password directly
    - Otherwise: Fetches from Azure Key Vault

    For AWS:
    - Fetches from AWS Secrets Manager
    """
    if _is_azure_environment():
        use_mi = os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"
        if use_mi:
            return _get_azure_db_token()

        # Check for direct password
        env_password = os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # Fetch from Key Vault
        return _get_azure_keyvault_password()
    else:
        return _get_aws_db_password()


def _get_db_url() -> str:
    # construct db url from env variables - try ALEMBIC_* first, fallback to SERVER_*
    DB_SCHEME = os.getenv("ALEMBIC_DB_SCHEME") or os.getenv("SERVER_DB_SCHEME") or "postgresql+psycopg"
    DB_USER = os.getenv("ALEMBIC_DB_USER") or os.getenv("SERVER_DB_USER") or "postgres"
    DB_HOST = os.getenv("ALEMBIC_DB_HOST") or os.getenv("SERVER_DB_HOST") or "localhost"
    DB_PORT = os.getenv("ALEMBIC_DB_PORT") or os.getenv("SERVER_DB_PORT") or "5432"
    DB_NAME = os.getenv("ALEMBIC_DB_NAME") or os.getenv("SERVER_DB_NAME") or "my_app_db"
    DB_PASSWORD = _get_db_password()
    return f"{DB_SCHEME}://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=_get_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_db_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
