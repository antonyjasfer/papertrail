import importlib
import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "app.services.document_storage",
        "app.services.document_intelligence",
        "app.core.contracts.storage",
        "app.core.contracts.repositories",
        "app.core.contracts.state_manager",
        "app.orchestration.models",
        "app.orchestration.errors",
        "app.orchestration.outbox",
        "app.orchestration.state_manager",
        "app.orchestration.orchestrator",
        "app.orchestration.pipeline",
        "app.api.routes.documents",
        "app.api.routes.orchestration",
        "app.main",
    ],
)
def test_clean_module_import(module_name: str):
    """Ensure modules can be imported cleanly without circular import errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None
