import json
import os
from datetime import datetime, timedelta
from logging.config import fileConfig

from alembic import context
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from aci.common.db.sql_models import Base

load_dotenv()

# Cache for database tokens/passwords
_db_credential_cache: tuple[str, datetime] | None = None

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


def _check_and_get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Environment variable '{name}' is not set")
    if value == "":
        raise ValueError(f"Environment variable '{name}' is empty string")
    return value


def _get_db_credential() -> str:
    """
    Fetches the database authentication credential (password or token).

    Behavior depends on configuration:
    - If USE_AZURE_MANAGED_IDENTITY=true: Fetches Azure Database token via Managed Identity
    - Else: Fetches password from environment or Azure Key Vault

    Tokens are cached and auto-refreshed 5 minutes before expiry.
    """
    global _db_credential_cache

    # Check for Managed Identity mode (try both ALEMBIC and SERVER variants)
    use_managed_identity = (
        os.getenv("ALEMBIC_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"
        or os.getenv("SERVER_USE_AZURE_MANAGED_IDENTITY", "false").lower() == "true"
    )

    if use_managed_identity:
        # Return cached token if still valid (refresh 5 minutes before expiry)
        if _db_credential_cache is not None:
            credential, expiry_time = _db_credential_cache
            if datetime.utcnow() < (expiry_time - timedelta(minutes=5)):
                return credential

        try:
            # Get token for Azure Database (works for PostgreSQL, MySQL, MariaDB, etc.)
            credential = DefaultAzureCredential()
            token_credential = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")

            # Cache token with expiry time (Azure tokens are typically valid for 1 hour)
            expiry_time = datetime.utcnow() + timedelta(hours=1)
            _db_credential_cache = (token_credential.token, expiry_time)

            return token_credential.token
        except Exception as e:
            raise RuntimeError(
                f"Failed to obtain Azure Database token using Managed Identity: {e}. "
                "Ensure the application has appropriate Azure RBAC permissions for database access."
            ) from e
    else:
        # Password-based authentication (local dev or Key Vault)
        env_password = os.getenv("ALEMBIC_DB_PASSWORD") or os.getenv("SERVER_DB_PASSWORD")
        if env_password:
            return env_password

        # For production, fetch from Azure Key Vault
        try:
            keyvault_url = _check_and_get_env_variable("AZURE_KEYVAULT_URL_FOR_DB")
            secret_name = _check_and_get_env_variable("AZURE_DB_SECRET_NAME")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=keyvault_url, credential=credential)
            secret = client.get_secret(secret_name)
            secret_dict = json.loads(secret.value)
            return secret_dict["password"]
        except ValueError as e:
            # If Azure Key Vault variables are not set, raise an error
            raise RuntimeError(
                "Database password not found. Either set ALEMBIC_DB_PASSWORD/SERVER_DB_PASSWORD "
                "for local development, or configure AZURE_KEYVAULT_URL_FOR_DB and AZURE_DB_SECRET_NAME "
                "for production."
            ) from e


def _get_db_url() -> str:
    """
    Constructs database URL for migrations.
    Automatically handles both Managed Identity and password-based authentication.
    """
    # construct db url from env variables - try ALEMBIC_* first, fallback to SERVER_*
    DB_SCHEME = os.getenv("ALEMBIC_DB_SCHEME") or os.getenv("SERVER_DB_SCHEME") or "postgresql+psycopg"
    DB_USER = os.getenv("ALEMBIC_DB_USER") or os.getenv("SERVER_DB_USER") or "postgres"
    DB_HOST = os.getenv("ALEMBIC_DB_HOST") or os.getenv("SERVER_DB_HOST") or "localhost"
    DB_PORT = os.getenv("ALEMBIC_DB_PORT") or os.getenv("SERVER_DB_PORT") or "5432"
    DB_NAME = os.getenv("ALEMBIC_DB_NAME") or os.getenv("SERVER_DB_NAME") or "my_app_db"

    # Get credential (password or token) - automatically handles both modes
    DB_CREDENTIAL = _get_db_credential()

    return f"{DB_SCHEME}://{DB_USER}:{DB_CREDENTIAL}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


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
