import os

from aci.common.utils import check_and_get_env_variable

# Azure Key Vault config — when set, takes precedence over AWS KMS for encryption.
# AZURE_KEY_ENCRYPTION_KEY_NAME: name of the key in the vault (e.g. "aci-encryption-key")
# AZURE_KEY_VAULT_URL: vault endpoint (e.g. "https://my-vault.vault.azure.net/")
AZURE_KEY_ENCRYPTION_KEY_NAME = os.getenv("AZURE_KEY_ENCRYPTION_KEY_NAME")
AZURE_KEY_VAULT_URL = os.getenv("AZURE_KEY_VAULT_URL")

# AWS KMS config — required when Azure Key Vault is not configured.
# When Azure mode is active these vars are optional (os.getenv), otherwise they are required.
if AZURE_KEY_ENCRYPTION_KEY_NAME:
    AWS_REGION = os.getenv("COMMON_AWS_REGION") or None
    AWS_ENDPOINT_URL = os.getenv("COMMON_AWS_ENDPOINT_URL") or None
    KEY_ENCRYPTION_KEY_ARN = os.getenv("COMMON_KEY_ENCRYPTION_KEY_ARN") or None
else:
    AWS_REGION = check_and_get_env_variable("COMMON_AWS_REGION")
    # AWS_ENDPOINT_URL can be empty for production (uses default AWS endpoints)
    # Only set this for LocalStack or custom endpoints
    AWS_ENDPOINT_URL = os.getenv("COMMON_AWS_ENDPOINT_URL") or None
    KEY_ENCRYPTION_KEY_ARN = check_and_get_env_variable("COMMON_KEY_ENCRYPTION_KEY_ARN")

API_KEY_HASHING_SECRET = check_and_get_env_variable("COMMON_API_KEY_HASHING_SECRET")
