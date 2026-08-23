from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel

from app.orchestration.errors import (
    OrchestrationError,
    StateSynchronizationError,
    UnauthorizedReviewerError,
)
from app.orchestration.models import HumanReviewPayload
from app.orchestration.pipeline import PipelineRunner

router = APIRouter(prefix="/api/v1/pipeline", tags=["orchestration"])
runner = PipelineRunner()


class StartPipelineRequest(BaseModel):
    document_id: str
    workflow_id: Optional[str] = None


class ResumePipelineRequest(BaseModel):
    payload: HumanReviewPayload


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_pipeline(req: StartPipelineRequest) -> Dict[str, Any]:
    """Start a new document analysis pipeline workflow."""
    try:
        w_id = runner.start_pipeline(document_id=req.document_id, workflow_id=req.workflow_id)
        # Synchronously advance pipeline steps in development/testing mode
        runner.run_to_completion(w_id)
        return runner.get_pipeline_status(w_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start pipeline: {e}",
        )


@router.get("/{workflow_id}/status")
async def get_pipeline_status(workflow_id: str) -> Dict[str, Any]:
    """Retrieve current status of an analysis pipeline workflow."""
    result = runner.get_pipeline_status(workflow_id)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    return result


@router.post("/{workflow_id}/resume")
async def resume_pipeline(
    workflow_id: str,
    req: ResumePipelineRequest,
    x_reviewer_principal: Optional[str] = Header(None, alias="X-Reviewer-Principal"),
) -> Dict[str, Any]:
    """Resume a workflow stalled in REQUIRES_REVIEW state following human review approval.
    
    Requires an authenticated reviewer principal header (X-Reviewer-Principal).
    """
    if not x_reviewer_principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authenticated reviewer header 'X-Reviewer-Principal'.",
        )

    try:
        runner.orchestrator.resume_workflow(
            workflow_id=workflow_id,
            payload=req.payload,
            reviewer_principal=x_reviewer_principal,
        )
        # Advance pipeline to completion
        runner.run_to_completion(workflow_id)
        return runner.get_pipeline_status(workflow_id)
    except UnauthorizedReviewerError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        )
    except StateSynchronizationError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )
    except OrchestrationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume pipeline: {err}",
        )
