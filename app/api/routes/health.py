from typing import Any, Dict
from fastapi import APIRouter
from app.core.config import settings
from app.core.metrics import metrics

router = APIRouter()


@router.get("/health", tags=["Health"])
def get_health_status() -> Dict[str, Any]:
    """Health check endpoint to verify server initialization and configuration."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "phase": settings.phase,
    }


@router.get("/health/ready", tags=["Health"])
def get_readiness_status() -> Dict[str, Any]:
    """Readiness check endpoint verifying configuration and environment readiness."""
    provider = settings.papertrail_cloud_provider.lower()
    
    # Assess dependency readiness context safely
    dep_status = {}
    if provider == "azure":
        dep_status["cosmos_db"] = "configured" if settings.azure_cosmos_endpoint else "unconfigured"
        dep_status["blob_storage"] = "configured" if settings.azure_storage_account_url else "unconfigured"
        dep_status["service_bus"] = "configured" if settings.azure_servicebus_namespace else "unconfigured"
        dep_status["key_vault"] = "configured" if settings.azure_keyvault_url else "unconfigured"
    elif provider == "gcp":
        dep_status["firestore"] = "configured" if settings.gcp_project_id else "unconfigured"
        dep_status["cloud_storage"] = "configured" if settings.gcs_bucket_documents else "unconfigured"
        dep_status["pubsub"] = "configured" if settings.pubsub_topic_workflow_events else "unconfigured"
    else:
        dep_status["in_memory"] = "configured"

    return {
        "status": "ready",
        "service": settings.app_name,
        "provider": settings.papertrail_cloud_provider,
        "environment": settings.environment,
        "dependencies": dep_status,
    }


@router.get("/metrics", tags=["Observability"])
def get_metrics_snapshot() -> Dict[str, Any]:
    """Expose application-level metrics snapshot for operational observability."""
    return metrics.get_snapshot()
