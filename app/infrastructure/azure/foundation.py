import logging
from typing import Any, Optional
from app.core.config import settings

logger = logging.getLogger("papertrail.azure.foundation")


class AzureFoundation:
    """Centralized Microsoft Azure client foundation manager.

    Provides client initialization helpers for Cosmos DB, Azure Blob Storage,
    Azure Service Bus, and Azure Key Vault without auto-connecting on module import.
    Enforces ManagedIdentityCredential in production and supports developer fallbacks in dev.
    """

    def __init__(self) -> None:
        self.environment = settings.environment
        self.cosmos_endpoint = settings.azure_cosmos_endpoint
        self.cosmos_key = settings.azure_cosmos_key
        self.storage_account_url = settings.azure_storage_account_url
        self.storage_connection_string = settings.azure_storage_connection_string
        self.servicebus_namespace = settings.azure_servicebus_namespace
        self.servicebus_connection_string = settings.azure_servicebus_connection_string
        self.keyvault_url = settings.azure_keyvault_url

    def get_credential(self) -> Any:
        """Initialize and return appropriate Azure credential based on environment."""
        if self.environment == "production":
            try:
                from azure.identity import ManagedIdentityCredential
                return ManagedIdentityCredential()
            except Exception as err:
                logger.error(
                    "Failed to initialize ManagedIdentityCredential in production: %s. Failing closed.",
                    err,
                )
                raise RuntimeError(
                    f"ManagedIdentityCredential unavailable in production environment: {err}"
                ) from err
        else:
            try:
                from azure.identity import DefaultAzureCredential
                return DefaultAzureCredential(exclude_shared_token_cache_credential=True)
            except Exception as err:
                logger.warning(
                    "DefaultAzureCredential unavailable in environment '%s' (%s).",
                    self.environment,
                    err,
                )
                return None

    def get_cosmos_client(self) -> Optional[Any]:
        """Initialize and return Azure Cosmos DB Client."""
        if not self.cosmos_endpoint:
            return None
        try:
            from azure.cosmos import CosmosClient
            if self.cosmos_key:
                return CosmosClient(self.cosmos_endpoint, credential=self.cosmos_key)
            cred = self.get_credential()
            if cred:
                return CosmosClient(self.cosmos_endpoint, credential=cred)
            return None
        except Exception as err:
            logger.warning("CosmosClient initialization error (%s).", err)
            return None

    def get_blob_service_client(self) -> Optional[Any]:
        """Initialize and return Azure BlobServiceClient."""
        if self.storage_connection_string:
            try:
                from azure.storage.blob import BlobServiceClient
                return BlobServiceClient.from_connection_string(self.storage_connection_string)
            except Exception as err:
                logger.warning("BlobServiceClient connection string error (%s).", err)
                return None
        if not self.storage_account_url:
            return None
        try:
            from azure.storage.blob import BlobServiceClient
            cred = self.get_credential()
            if cred:
                return BlobServiceClient(account_url=self.storage_account_url, credential=cred)
            return None
        except Exception as err:
            logger.warning("BlobServiceClient initialization error (%s).", err)
            return None

    def get_servicebus_client(self) -> Optional[Any]:
        """Initialize and return Azure ServiceBusClient."""
        if self.servicebus_connection_string:
            try:
                from azure.servicebus import ServiceBusClient
                return ServiceBusClient.from_connection_string(self.servicebus_connection_string)
            except Exception as err:
                logger.warning("ServiceBusClient connection string error (%s).", err)
                return None
        if not self.servicebus_namespace:
            return None
        try:
            from azure.servicebus import ServiceBusClient
            cred = self.get_credential()
            if cred:
                return ServiceBusClient(
                    fully_qualified_namespace=self.servicebus_namespace, credential=cred
                )
            return None
        except Exception as err:
            logger.warning("ServiceBusClient initialization error (%s).", err)
            return None

    def get_keyvault_secret_client(self) -> Optional[Any]:
        """Initialize and return Azure Key Vault SecretClient."""
        if not self.keyvault_url:
            return None
        try:
            from azure.keyvault.secrets import SecretClient
            cred = self.get_credential()
            if cred:
                return SecretClient(vault_url=self.keyvault_url, credential=cred)
            return None
        except Exception as err:
            logger.warning("SecretClient initialization error (%s).", err)
            return None


azure_foundation = AzureFoundation()
