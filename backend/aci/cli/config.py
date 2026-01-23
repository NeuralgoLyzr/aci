import os

from dotenv import load_dotenv

from aci.common.utils import (
    check_and_get_env_variable,
    construct_db_url,
    construct_db_url_sync,
    get_environment,
    get_wtw_config,
    is_azure_environment,
    is_wtw_environment,
    map_wtw_model_name,
)

load_dotenv()

DEV_ENV = get_environment()  # AWS, AZURE, or AZURE/WTW

# LLM Configuration - differs based on environment
if is_wtw_environment():
    # AZURE/WTW configuration - uses WTW-specific endpoints
    WTW_CONFIG = get_wtw_config()
    WTW_API_BASE = WTW_CONFIG["wtw_api_base"]
    WTW_API_VERSION = WTW_CONFIG["wtw_api_version"]
    WTW_API_SCOPE = WTW_CONFIG["wtw_api_scope"]

    # WTW uses deployment names mapped from standard model names
    _wtw_embedding_model = os.getenv("WTW_EMBEDDING_MODEL", "text-embedding-3-small")
    OPENAI_EMBEDDING_MODEL = map_wtw_model_name(_wtw_embedding_model, is_embedding=True)
    OPENAI_EMBEDDING_DIMENSION = int(check_and_get_env_variable("CLI_OPENAI_EMBEDDING_DIMENSION"))

    # For compatibility - WTW uses Managed Identity, no API key needed
    OPENAI_API_KEY = ""
    AZURE_OPENAI_ENDPOINT = WTW_API_BASE
    AZURE_OPENAI_API_KEY = None
    AZURE_OPENAI_API_VERSION = WTW_API_VERSION
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = OPENAI_EMBEDDING_MODEL

elif is_azure_environment():
    # Standard Azure OpenAI configuration
    AZURE_OPENAI_ENDPOINT = check_and_get_env_variable("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")  # Optional if using Managed Identity
    AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = check_and_get_env_variable("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    OPENAI_EMBEDDING_DIMENSION = int(check_and_get_env_variable("CLI_OPENAI_EMBEDDING_DIMENSION"))

    # For compatibility with existing code
    OPENAI_API_KEY = AZURE_OPENAI_API_KEY or ""
    OPENAI_EMBEDDING_MODEL = AZURE_OPENAI_EMBEDDING_DEPLOYMENT

    # WTW variables not used in standard Azure
    WTW_CONFIG = None
    WTW_API_BASE = None
    WTW_API_VERSION = None
    WTW_API_SCOPE = None

else:
    # Standard OpenAI configuration (AWS environment)
    OPENAI_API_KEY = check_and_get_env_variable("CLI_OPENAI_API_KEY")
    OPENAI_EMBEDDING_MODEL = check_and_get_env_variable("CLI_OPENAI_EMBEDDING_MODEL")
    OPENAI_EMBEDDING_DIMENSION = int(check_and_get_env_variable("CLI_OPENAI_EMBEDDING_DIMENSION"))

    # Azure/WTW variables not used in AWS
    AZURE_OPENAI_ENDPOINT = None
    AZURE_OPENAI_API_KEY = None
    AZURE_OPENAI_API_VERSION = None
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = None
    WTW_CONFIG = None
    WTW_API_BASE = None
    WTW_API_VERSION = None
    WTW_API_SCOPE = None

DB_SCHEME = check_and_get_env_variable("CLI_DB_SCHEME")
DB_USER = check_and_get_env_variable("CLI_DB_USER")
DB_HOST = check_and_get_env_variable("CLI_DB_HOST")
DB_PORT = check_and_get_env_variable("CLI_DB_PORT")
DB_NAME = check_and_get_env_variable("CLI_DB_NAME")
SERVER_URL = check_and_get_env_variable("CLI_SERVER_URL")

# DB_FULL_URL will be initialized asynchronously by calling get_db_full_url()
DB_FULL_URL: str | None = None


def get_db_full_url_sync() -> str:
    """
    Lazily initializes and returns the database URL synchronously.
    Fetches password from AWS Secrets Manager on first call.
    """
    global DB_FULL_URL
    if DB_FULL_URL is not None:
        return DB_FULL_URL

    DB_FULL_URL = construct_db_url_sync(DB_SCHEME, DB_USER, DB_HOST, DB_PORT, DB_NAME)
    return DB_FULL_URL


async def get_db_full_url() -> str:
    """
    Lazily initializes and returns the database URL asynchronously.
    Fetches password from AWS Secrets Manager on first call.
    """
    global DB_FULL_URL
    if DB_FULL_URL is not None:
        return DB_FULL_URL

    DB_FULL_URL = await construct_db_url(DB_SCHEME, DB_USER, DB_HOST, DB_PORT, DB_NAME)
    return DB_FULL_URL


# OpenAI client singleton
_openai_client = None


def get_openai_client():
    """
    Get the OpenAI client instance (singleton pattern).
    Returns AzureOpenAI for Azure environments, standard OpenAI for AWS.
    """
    global _openai_client
    if _openai_client is None:
        from aci.common.utils import get_openai_client as create_openai_client

        _openai_client = create_openai_client(
            api_key=OPENAI_API_KEY if OPENAI_API_KEY else None,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_api_version=AZURE_OPENAI_API_VERSION,
        )
    return _openai_client
