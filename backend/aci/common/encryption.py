import hashlib
import hmac
import os
import struct
from typing import cast

import aws_encryption_sdk  # type: ignore
import boto3  # type: ignore
from aws_cryptographic_material_providers.mpl import (  # type: ignore
    AwsCryptographicMaterialProviders,
)
from aws_cryptographic_material_providers.mpl.config import MaterialProvidersConfig  # type: ignore
from aws_cryptographic_material_providers.mpl.models import CreateAwsKmsKeyringInput  # type: ignore
from aws_cryptographic_material_providers.mpl.references import IKeyring  # type: ignore
from aws_encryption_sdk import CommitmentPolicy

from aci.common import config

client = aws_encryption_sdk.EncryptionSDKClient(
    commitment_policy=CommitmentPolicy.REQUIRE_ENCRYPT_REQUIRE_DECRYPT
)

# Lazy initialization of KMS / Azure Key Vault resources
_kms_keyring: IKeyring | None = None
_azure_crypto_client: object | None = None


def _get_kms_keyring() -> IKeyring:
    """Lazy initialization of KMS keyring to avoid errors in local environment."""
    global _kms_keyring
    if _kms_keyring is None:
        kms_client = boto3.client(
            "kms",
            region_name=config.AWS_REGION,
            endpoint_url=config.AWS_ENDPOINT_URL,
        )

        mat_prov: AwsCryptographicMaterialProviders = AwsCryptographicMaterialProviders(
            config=MaterialProvidersConfig()
        )

        keyring_input: CreateAwsKmsKeyringInput = CreateAwsKmsKeyringInput(
            kms_key_id=config.KEY_ENCRYPTION_KEY_ARN,
            kms_client=kms_client,
        )

        _kms_keyring = mat_prov.create_aws_kms_keyring(input=keyring_input)
    return _kms_keyring


def _get_azure_crypto_client() -> object:
    """Lazy initialization of Azure Key Vault CryptographyClient."""
    global _azure_crypto_client
    if _azure_crypto_client is None:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.keyvault.keys import KeyClient  # type: ignore
        from azure.keyvault.keys.crypto import CryptographyClient  # type: ignore

        credential = DefaultAzureCredential()
        key_client = KeyClient(vault_url=config.AZURE_KEY_VAULT_URL, credential=credential)
        key = key_client.get_key(config.AZURE_KEY_ENCRYPTION_KEY_NAME)
        _azure_crypto_client = CryptographyClient(key, credential=credential)
    return _azure_crypto_client


def _azure_encrypt(plain_data: bytes) -> bytes:
    """Envelope encryption: AES-256-GCM for data, Azure Key Vault RSA-OAEP-256 for DEK wrapping.

    Wire format: [4-byte big-endian wrapped_dek_len][wrapped_dek][12-byte nonce][GCM ciphertext+tag]
    """
    import secrets

    from azure.keyvault.keys.crypto import CryptographyClient  # type: ignore
    from azure.keyvault.keys.crypto import KeyWrapAlgorithm  # type: ignore
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

    dek = secrets.token_bytes(32)  # 256-bit data encryption key
    nonce = secrets.token_bytes(12)  # 96-bit GCM nonce
    ciphertext = AESGCM(dek).encrypt(nonce, plain_data, None)

    crypto_client = cast(CryptographyClient, _get_azure_crypto_client())
    wrapped_dek = crypto_client.wrap_key(KeyWrapAlgorithm.rsa_oaep_256, dek).encrypted_key

    return struct.pack(">I", len(wrapped_dek)) + wrapped_dek + nonce + ciphertext


def _azure_decrypt(cipher_data: bytes) -> bytes:
    """Envelope decryption: unwrap DEK via Azure Key Vault, then AES-256-GCM decrypt."""
    from azure.keyvault.keys.crypto import CryptographyClient  # type: ignore
    from azure.keyvault.keys.crypto import KeyWrapAlgorithm  # type: ignore
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

    offset = 0
    (wrapped_dek_len,) = struct.unpack_from(">I", cipher_data, offset)
    offset += 4
    wrapped_dek = cipher_data[offset : offset + wrapped_dek_len]
    offset += wrapped_dek_len
    nonce = cipher_data[offset : offset + 12]
    offset += 12
    ciphertext = cipher_data[offset:]

    crypto_client = cast(CryptographyClient, _get_azure_crypto_client())
    dek = crypto_client.unwrap_key(KeyWrapAlgorithm.rsa_oaep_256, wrapped_dek).key

    return AESGCM(dek).decrypt(nonce, ciphertext, None)


def encrypt(plain_data: bytes) -> bytes:
    # Skip encryption in local environment (for development)
    if os.getenv("SERVER_ENVIRONMENT") == "local":
        return plain_data

    if config.AZURE_KEY_ENCRYPTION_KEY_NAME:
        return _azure_encrypt(plain_data)

    # TODO: ignore encryptor_header for now
    my_ciphertext, _ = client.encrypt(source=plain_data, keyring=_get_kms_keyring())
    return cast(bytes, my_ciphertext)


def decrypt(cipher_data: bytes) -> bytes:
    # Skip decryption in local environment (for development)
    if os.getenv("SERVER_ENVIRONMENT") == "local":
        return cipher_data

    if config.AZURE_KEY_ENCRYPTION_KEY_NAME:
        return _azure_decrypt(cipher_data)

    # TODO: ignore decryptor_header for now
    my_plaintext, _ = client.decrypt(source=cipher_data, keyring=_get_kms_keyring())
    return cast(bytes, my_plaintext)


def hmac_sha256(message: str) -> str:
    return hmac.new(
        config.API_KEY_HASHING_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
