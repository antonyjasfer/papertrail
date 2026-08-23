from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ISecretProvider(Protocol):
    """Protocol for secrets management providers (Google Secret Manager, Azure Key Vault, Env)."""

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> str: ...
