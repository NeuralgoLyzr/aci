import hashlib
import hmac
import os
from typing import cast

from aci.common import config
from aci.common.utils import is_azure_environment

# Only import AWS encryption SDK when not in Azure environment
if not is_azure_environment() and os.getenv("SERVER_ENVIRONMENT") != "local":
    import aws_encryption_sdk  # type: ignore
    import boto3  # type: ignore
    from aws_cryptographic_material_providers.mpl import (  # type: ignore
        AwsCryptographicMaterialProviders,
    )
    from aws_cryptographic_material_providers.mpl.config import MaterialProvidersConfig  # type: ignore
    from aws_cryptographic_material_providers.mpl.models import CreateAwsKmsKeyringInput  # type: ignore
    from aws_cryptographic_material_providers.mpl.references import IKeyring  # type: ignore
    from aws_encryption_sdk import CommitmentPolicy

    client = aws_encryption_sdk.EncryptionSDKClient(
        commitment_policy=CommitmentPolicy.REQUIRE_ENCRYPT_REQUIRE_DECRYPT
    )

    # Lazy initialization of KMS resources
    _kms_keyring: IKeyring | None = None


def _get_kms_keyring():
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


def encrypt(plain_data: bytes) -> bytes:
    # Skip encryption in local or Azure environment
    if os.getenv("SERVER_ENVIRONMENT") == "local" or is_azure_environment():
        return plain_data

    # TODO: ignore encryptor_header for now
    my_ciphertext, _ = client.encrypt(source=plain_data, keyring=_get_kms_keyring())
    return cast(bytes, my_ciphertext)


def decrypt(cipher_data: bytes) -> bytes:
    # Skip decryption in local or Azure environment
    if os.getenv("SERVER_ENVIRONMENT") == "local" or is_azure_environment():
        return cipher_data

    # TODO: ignore decryptor_header for now
    my_plaintext, _ = client.decrypt(source=cipher_data, keyring=_get_kms_keyring())
    return cast(bytes, my_plaintext)


def hmac_sha256(message: str) -> str:
    return hmac.new(
        config.API_KEY_HASHING_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
