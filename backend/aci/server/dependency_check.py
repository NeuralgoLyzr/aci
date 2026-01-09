import os
import traceback
from aci.common.encryption import decrypt, encrypt
from aci.common.exceptions import DependencyCheckError


def check_azure_keyvault_dependency() -> None:
    check_data = b"start up dependency check"

    try:
        encrypted_data = encrypt(check_data)
        decrypted_data = decrypt(encrypted_data)

        if check_data != decrypted_data:
            raise DependencyCheckError(
                f"Encryption/decryption using Azure Key Vault failed: original data '{check_data!r}'"
                f"does not match decrypted result '{decrypted_data!r}'"
            )
    except Exception as e:
        # Provide more detailed error information
        error_msg = (
            f"Azure Key Vault dependency check failed: {type(e).__name__}: {str(e)}\n"
            f"This usually indicates a permissions or configuration issue.\n"
            f"Please check:\n"
            f"1. The Key Vault exists and is accessible\n"
            f"2. Your authentication credentials are valid (DefaultAzureCredential)\n"
            f"3. Your identity has 'Get' permission on secrets in the Key Vault\n"
            f"4. The COMMON_AZURE_KEYVAULT_URL is correct\n"
            f"5. The COMMON_AZURE_ENCRYPTION_KEY_NAME exists in the Key Vault\n\n"
            f"Full traceback:\n{traceback.format_exc()}"
        )
        raise DependencyCheckError(error_msg) from e


def check_dependencies() -> None:
    # Skip Key Vault check only in local environment (for development)
    if os.getenv("SERVER_ENVIRONMENT") == "local":
        print("Skipping Azure Key Vault dependency check for local environment")
        return

    check_azure_keyvault_dependency()
