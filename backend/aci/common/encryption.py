import base64
import hashlib
import hmac
import os
import secrets

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from aci.common import config

# Lazy initialization of Azure Key Vault client
_keyvault_client: SecretClient | None = None


def _get_keyvault_client() -> SecretClient:
    """Lazy initialization of Azure Key Vault client."""
    global _keyvault_client
    if _keyvault_client is None:
        credential = DefaultAzureCredential()
        _keyvault_client = SecretClient(
            vault_url=config.AZURE_KEYVAULT_URL, credential=credential
        )
    return _keyvault_client


def _get_encryption_key() -> bytes:
    """
    Retrieve the encryption key from Azure Key Vault.
    The key is stored as a secret in the Key Vault and should be a base64-encoded 32-byte key.
    """
    client = _get_keyvault_client()
    secret = client.get_secret(config.AZURE_ENCRYPTION_KEY_NAME)
    # The secret value should be the base64-encoded key
    return base64.b64decode(secret.value)


def encrypt(plain_data: bytes) -> bytes:
    """
    Encrypt data using AES-256-GCM with a key from Azure Key Vault.
    Skip encryption in local environment (for development).
    Returns: IV (16 bytes) + ciphertext + tag (16 bytes)
    """
    # Skip encryption in local environment (for development)
    if os.getenv("SERVER_ENVIRONMENT") == "local":
        return plain_data

    try:
        key = _get_encryption_key()
    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve encryption key from Azure Key Vault: {str(e)}"
        ) from e

    # Generate random IV (initialization vector)
    iv = secrets.token_bytes(16)

    # Create cipher in GCM mode
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(iv),
    )
    encryptor = cipher.encryptor()

    # Encrypt the data
    ciphertext = encryptor.update(plain_data) + encryptor.finalize()

    # Return IV + ciphertext + tag
    return iv + ciphertext + encryptor.tag


def decrypt(cipher_data: bytes) -> bytes:
    """
    Decrypt data that was encrypted with AES-256-GCM.
    Expects: IV (16 bytes) + ciphertext + tag (16 bytes)
    Skip decryption in local environment (for development).
    """
    # Skip decryption in local environment (for development)
    if os.getenv("SERVER_ENVIRONMENT") == "local":
        return cipher_data

    try:
        key = _get_encryption_key()
    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve encryption key from Azure Key Vault: {str(e)}"
        ) from e

    # Extract IV and ciphertext+tag
    iv = cipher_data[:16]
    ciphertext_with_tag = cipher_data[16:]

    # The tag is the last 16 bytes
    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]

    # Create cipher in GCM mode
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(iv, tag),
    )
    decryptor = cipher.decryptor()

    # Decrypt the data
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    return plaintext


def hmac_sha256(message: str) -> str:
    return hmac.new(
        config.API_KEY_HASHING_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
