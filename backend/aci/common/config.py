import os
from aci.common.utils import check_and_get_env_variable

# Azure Key Vault Configuration
AZURE_KEYVAULT_URL = check_and_get_env_variable("COMMON_AZURE_KEYVAULT_URL")
# Name of the key in Azure Key Vault used for data encryption
AZURE_ENCRYPTION_KEY_NAME = check_and_get_env_variable("COMMON_AZURE_ENCRYPTION_KEY_NAME")

API_KEY_HASHING_SECRET = check_and_get_env_variable("COMMON_API_KEY_HASHING_SECRET")
