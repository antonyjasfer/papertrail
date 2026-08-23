from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
def get_health_status():
    """Health check endpoint to verify server initialization and configuration."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "phase": settings.phase,
    }


@router.get("/health/ready", tags=["Health"])
def get_readiness_status():
    """Readiness check endpoint verifying configuration and environment readiness."""
    return {
        "status": "ready",
        "service": settings.app_name,
        "provider": settings.papertrail_cloud_provider,
        "environment": settings.environment,
    }

