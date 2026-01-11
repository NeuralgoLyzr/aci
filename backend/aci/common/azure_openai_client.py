"""
Azure OpenAI client factory and utilities.

This module provides helper functions to create and configure Azure OpenAI clients
for different deployment scenarios (embeddings, chat completions, etc.).
"""

from azure.ai.openai import AzureOpenAI
from typing import Optional

# Cache for Azure OpenAI client (lazy initialization)
_azure_openai_client: Optional[AzureOpenAI] = None


def get_azure_openai_client(
    api_key: str,
    endpoint: str,
    api_version: str = "2024-10-21",
) -> AzureOpenAI:
    """
    Create and return an Azure OpenAI client.

    Args:
        api_key: Azure OpenAI API key
        endpoint: Azure OpenAI endpoint URL (e.g., https://your-resource.openai.azure.com/)
        api_version: API version to use (default: 2024-10-21)

    Returns:
        Configured AzureOpenAI client instance
    """
    return AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )


def get_cached_azure_openai_client(
    api_key: str,
    endpoint: str,
    api_version: str = "2024-10-21",
) -> AzureOpenAI:
    """
    Get a cached Azure OpenAI client (singleton pattern).

    This function caches the client on first call and returns the same instance
    on subsequent calls. Use this for long-lived processes like the server.

    Args:
        api_key: Azure OpenAI API key
        endpoint: Azure OpenAI endpoint URL
        api_version: API version to use (default: 2024-10-21)

    Returns:
        Cached AzureOpenAI client instance
    """
    global _azure_openai_client
    if _azure_openai_client is None:
        _azure_openai_client = get_azure_openai_client(api_key, endpoint, api_version)
    return _azure_openai_client


def reset_cached_client() -> None:
    """Reset the cached Azure OpenAI client. Useful for testing."""
    global _azure_openai_client
    _azure_openai_client = None
