from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel

from app.api.dependencies import (
    get_workflow_orchestrator,
    get_workflow_state_manager,
)
from app.core.contracts.state_manager import IWorkflowStateManager
from app.orchestration.errors import (
    OrchestrationError,
    StateSynchronizationError,
    UnauthorizedReviewerError,
)
from app.orchestration.models import HumanReviewPayload
from app.orchestration.orchestrator import WorkflowOrchestrator

router = APIRouter(prefix="/api/v1/pipeline", tags=["orchestration"])


class StartPipelineRequest(BaseModel):
    document_id: str
    workflow_id: Optional[str] = None


class ResumePipelineRequest(BaseModel):
    payload: HumanReviewPayload


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_pipeline(
    req: StartPipelineRequest,
    orchestrator: WorkflowOrchestrator = Depends(get_workflow_orchestrator),
    state_manager: IWorkflowStateManager = Depends(get_workflow_state_manager),
) -> Dict[str, Any]:
    """Start a new document analysis pipeline workflow."""
    try:
        w_id = req.workflow_id or f"wf-{uuid.uuid4().hex[:8]}"
        workflow, _ = orchestrator.start_workflow(workflow_id=w_id, document_id=req.document_id)
        revision = state_manager.get_workflow_revision(w_id)
        return {
            "workflow_id": workflow.workflow_id,
            "document_id": workflow.document_id,
            "current_state": workflow.current_state.value,
            "workflow_revision": revision,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
            "failure_reason": workflow.failure_reason,
            "escalation_reason": workflow.escalation_reason,
            "review_reason": workflow.review_reason,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start pipeline: {e}",
        )


@router.get("/{workflow_id}/status")
async def get_pipeline_status(
    workflow_id: str,
    state_manager: IWorkflowStateManager = Depends(get_workflow_state_manager),
) -> Dict[str, Any]:
    """Retrieve current status of an analysis pipeline workflow."""
    workflow = state_manager.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{workflow_id}' not found.",
        )
    revision = state_manager.get_workflow_revision(workflow_id)
    return {
        "workflow_id": workflow.workflow_id,
        "document_id": workflow.document_id,
        "current_state": workflow.current_state.value,
        "workflow_revision": revision,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "failure_reason": workflow.failure_reason,
        "escalation_reason": workflow.escalation_reason,
        "review_reason": workflow.review_reason,
    }


@router.post("/{workflow_id}/resume")
async def resume_pipeline(
    workflow_id: str,
    req: ResumePipelineRequest,
    x_reviewer_principal: Optional[str] = Header(None, alias="X-Reviewer-Principal"),
    orchestrator: WorkflowOrchestrator = Depends(get_workflow_orchestrator),
    state_manager: IWorkflowStateManager = Depends(get_workflow_state_manager),
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
        workflow, _ = orchestrator.resume_workflow(
            workflow_id=workflow_id,
            payload=req.payload,
            reviewer_principal=x_reviewer_principal,
        )
        revision = state_manager.get_workflow_revision(workflow_id)
        return {
            "workflow_id": workflow.workflow_id,
            "document_id": workflow.document_id,
            "current_state": workflow.current_state.value,
            "workflow_revision": revision,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
            "failure_reason": workflow.failure_reason,
            "escalation_reason": workflow.escalation_reason,
            "review_reason": workflow.review_reason,
        }
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

