from typing import Union

from openai import AzureOpenAI, OpenAI

from aci.common.logging_setup import get_logger
from aci.common.schemas.app import AppEmbeddingFields
from aci.common.schemas.function import FunctionEmbeddingFields
from aci.common.utils import is_azure_environment

logger = get_logger(__name__)

# Type alias for OpenAI clients
OpenAIClient = Union[OpenAI, AzureOpenAI]


def generate_app_embedding(
    app: AppEmbeddingFields,
    openai_client: OpenAIClient,
    embedding_model: str,
    embedding_dimension: int,
) -> list[float]:
    """
    Generate embedding for app.
    TODO: what else should be included or not in the embedding?
    """
    logger.debug(f"Generating embedding for app: {app.name}...")
    # generate app embeddings based on app config's name, display_name, provider, description, categories
    text_for_embedding = app.model_dump_json()
    logger.debug(f"Text for app embedding: {text_for_embedding}")
    return generate_embedding(
        openai_client, embedding_model, embedding_dimension, text_for_embedding
    )


# TODO: batch generate function embeddings
# TODO: update app embedding to include function embeddings whenever functions are added/updated?
def generate_function_embeddings(
    functions: list[FunctionEmbeddingFields],
    openai_client: OpenAIClient,
    embedding_model: str,
    embedding_dimension: int,
) -> list[list[float]]:
    logger.debug(f"Generating embeddings for {len(functions)} functions...")
    function_embeddings: list[list[float]] = []
    for function in functions:
        function_embeddings.append(
            generate_function_embedding(
                function, openai_client, embedding_model, embedding_dimension
            )
        )

    return function_embeddings


def generate_function_embedding(
    function: FunctionEmbeddingFields,
    openai_client: OpenAIClient,
    embedding_model: str,
    embedding_dimension: int,
) -> list[float]:
    logger.debug(f"Generating embedding for function: {function.name}...")
    text_for_embedding = function.model_dump_json()
    logger.debug(f"Text for function embedding: {text_for_embedding}")
    return generate_embedding(
        openai_client, embedding_model, embedding_dimension, text_for_embedding
    )


# Models/deployments that support the dimensions parameter
# Includes both standard OpenAI model names and WTW deployment names
MODELS_WITH_DIMENSIONS_SUPPORT = {
    # Standard OpenAI
    "text-embedding-3-small",
    "text-embedding-3-large",
    # WTW deployment names
    "em3-small",
    "em3-large",
}


# TODO: allow different inference providers
# TODO: exponential backoff?
def generate_embedding(
    openai_client: OpenAIClient, embedding_model: str, embedding_dimension: int, text: str
) -> list[float]:
    """
    Generate an embedding for the given text using OpenAI's model.
    Works with both standard OpenAI and Azure OpenAI clients.

    Note: Azure OpenAI with text-embedding-ada-002 doesn't support the dimensions parameter.
    Only text-embedding-3-small and text-embedding-3-large support it.
    """
    logger.debug(f"Generating embedding for text: {text}")
    try:
        # Check if the model supports dimensions parameter
        # For Azure, embedding_model is the deployment name, so we check for known patterns
        supports_dimensions = any(
            model_name in embedding_model.lower()
            for model_name in ["text-embedding-3", "em3", "embedding-3"]
        )

        if is_azure_environment() and not supports_dimensions:
            # Azure OpenAI with ada-002 or similar - don't pass dimensions
            logger.debug(f"Azure environment detected, model {embedding_model} - not passing dimensions")
            response = openai_client.embeddings.create(
                input=[text],
                model=embedding_model,
            )
        else:
            # Standard OpenAI or Azure with text-embedding-3 models
            response = openai_client.embeddings.create(
                input=[text],
                model=embedding_model,
                dimensions=embedding_dimension,
            )

        embedding: list[float] = response.data[0].embedding
        return embedding
    except Exception:
        logger.error("Error generating embedding", exc_info=True)
        raise
