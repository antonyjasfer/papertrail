import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.contracts.secrets import ISecretProvider
from app.infrastructure.azure.foundation import azure_foundation

logger = logging.getLogger("papertrail.azure.key_vault")


class AzureKeyVaultSecretProvider:
    """Azure Key Vault Secret Provider implementing ISecretProvider protocol.
    
    Enforces fail-closed security: authentication, authorization, or network failures
    raise RuntimeError immediately and are never masked with fallback values.
    """

    def __init__(
        self,
        vault_url: Optional[str] = None,
        secret_client: Optional[Any] = None,
    ) -> None:
        self.vault_url = vault_url or settings.azure_keyvault_url
        self._client = secret_client
        self._in_memory_secrets: Dict[str, str] = {}

    @property
    def client(self) -> Optional[Any]:
        if self._client is None:
            self._client = azure_foundation.get_keyvault_secret_client()
        return self._client

    def set_in_memory_secret(self, secret_name: str, value: str) -> None:
        """Helper to seed secrets in mock/testing environments."""
        self._in_memory_secrets[secret_name] = value

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> str:
        """Retrieve secret from Azure Key Vault or fallback store.
        
        Raises:
            KeyError: If secret is not found and no default is provided.
            RuntimeError: If authentication, authorization, or network outage occurs (fail-closed).
        """
        # If client is active, query Key Vault
        if self.client is not None:
            try:
                from azure.core.exceptions import ResourceNotFoundError
                secret = self.client.get_secret(secret_name)
                return secret.value
            except Exception as err:
                # Check for ResourceNotFoundError specifically
                err_type = type(err).__name__
                if "ResourceNotFound" in err_type:
                    if default is not None:
                        return default
                    raise KeyError(f"Secret '{secret_name}' not found in Key Vault.") from err
                
                # FAIL CLOSED on authentication, authorization, or network outages
                logger.error(
                    "Fatal error accessing Key Vault for secret '%s': %s",
                    secret_name,
                    err,
                )
                raise RuntimeError(
                    f"Key Vault access failure for '{secret_name}': {err}"
                ) from err

        # In-memory mock fallback
        if secret_name in self._in_memory_secrets:
            return self._in_memory_secrets[secret_name]
        if default is not None:
            return default
        raise KeyError(f"Secret '{secret_name}' not found in mock secrets store.")
