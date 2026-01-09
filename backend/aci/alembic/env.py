import json
import os
from logging.config import fileConfig

from alembic import context
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
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


def _check_and_get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Environment variable '{name}' is not set")
    if value == "":
        raise ValueError(f"Environment variable '{name}' is empty string")
    return value


def _get_db_password() -> str:
    """
    Fetches the DB password from Azure Key Vault.
    For local development, falls back to environment variables.
    """
    # Try to get from environment variable first (for local development)
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
