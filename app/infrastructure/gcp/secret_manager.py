import logging
import os
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.contracts.secrets import ISecretProvider
from app.core.gcp import gcp_foundation

logger = logging.getLogger("papertrail.gcp.secret_manager")


class GCPSecretManagerProvider:
    """Google Cloud Secret Manager Provider implementing ISecretProvider protocol.
    
    Supports Application Default Credentials (ADC) in Google Cloud Run / Compute Engine
    and graceful environment fallback for local development and test mocking.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        secret_client: Optional[Any] = None,
    ) -> None:
        self.project_id = project_id or settings.gcp_project_id
        self._client = secret_client
        self._in_memory_secrets: Dict[str, str] = {}

    @property
    def client(self) -> Optional[Any]:
        if self._client is None:
            self._client = gcp_foundation.get_secret_manager_client()
        return self._client

    def set_in_memory_secret(self, secret_name: str, value: str) -> None:
        """Helper to seed secrets for unit and integration testing."""
        self._in_memory_secrets[secret_name] = value

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> str:
        """Retrieve secret value from Google Cloud Secret Manager.
        
        Args:
            secret_name: Name of the secret (e.g. 'gemini-api-key').
            default: Optional default value if secret is not found.
            
        Returns:
            The string secret payload.
            
        Raises:
            KeyError: If secret is not found and no default is provided.
            RuntimeError: If authentication or network communication fails.
        """
        # 1. Check in-memory secrets (test mocking)
        if secret_name in self._in_memory_secrets:
            return self._in_memory_secrets[secret_name]

        # 2. Check live Google Cloud Secret Manager client
        if self.client is not None:
            try:
                resource_name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
                response = self.client.access_secret_version(request={"name": resource_name})
                payload_str = response.payload.data.decode("utf-8")
                return payload_str
            except Exception as err:
                err_str = str(err).lower()
                if "not found" in err_str or "404" in err_str:
                    logger.warning(
                        "[GCPSecretManager] Secret '%s' not found in project '%s'.",
                        secret_name,
                        self.project_id,
                    )
                else:
                    logger.error(
                        "[GCPSecretManager] Failed accessing secret '%s': %s",
                        secret_name,
                        err,
                    )
                    raise RuntimeError(f"GCP Secret Manager access failure: {err}") from err

        # 3. Environment variable fallback (converts kebab-case to SNAKE_CASE)
        env_key = secret_name.upper().replace("-", "_")
        if env_key in os.environ:
            return os.environ[env_key]

        if default is not None:
            return default

        raise KeyError(f"Secret '{secret_name}' was not found in GCP Secret Manager or environment.")
