import logging
from datetime import datetime
from typing import Optional

from app.agents.document_intelligence.agent import (
    DocumentIntelligenceAgent,
    DocumentIntelligenceAgentError,
)
from app.core.config import settings
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    GeminiExtractionPayload,
)
from app.services.document_storage import DocumentStorageService, DocumentStorageError

logger = logging.getLogger("papertrail.services.document_intelligence")


class DocumentIntelligenceService:
    """Service managing document loading from storage, agent invocation, confidence evaluation,
    and deterministic Python AnalysisStatus computation.
    """

    def __init__(
        self,
        storage_service: Optional[DocumentStorageService] = None,
        agent: Optional[DocumentIntelligenceAgent] = None,
        confidence_threshold: Optional[float] = None,
    ):
        if storage_service is not None:
            self.storage_service = storage_service
        else:
            from app.api.dependencies import get_document_storage_service
            self.storage_service = get_document_storage_service()
        self.agent = agent or DocumentIntelligenceAgent()
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.document_extraction_confidence_threshold
        )

    def validate_date_representations(self, dates: list) -> list:
        """Validate and log extracted dates for ISO-8601 formatting consistency."""
        validated_dates = []
        for date_str in dates:
            if not date_str or not isinstance(date_str, str):
                continue
            cleaned = date_str.strip()
            validated_dates.append(cleaned)
        return validated_dates

    def validate_financial_representations(self, amounts: list) -> list:
        """Validate monetary string representations for precise decimal formatting."""
        validated_amounts = []
        for amt in amounts:
            if amt is None:
                continue
            cleaned = str(amt).strip()
            validated_amounts.append(cleaned)
        return validated_amounts

    def analyze_document(self, document_id: str) -> DocumentExtractionResult:
        """Analyze a stored document by retrieving byte payload from DocumentStorageService,
        executing DocumentIntelligenceAgent extraction, and computing AnalysisStatus deterministically.
        """
        logger.info("Initiating Document Intelligence Analysis for document '%s'", document_id)

        # Step 1: Retrieve Document Metadata & Payload via Storage Service Boundary
        try:
            metadata = self.storage_service.get_document_metadata(document_id)
            file_bytes = self.storage_service.get_document_bytes(document_id)
        except DocumentStorageError as storage_err:
            logger.error("Failed to load document '%s' from storage service: %s", document_id, storage_err)
            return DocumentExtractionResult(
                extraction=None,
                status=AnalysisStatus.FAILED,
                status_reason=f"Storage access error: {storage_err}",
            )
        except Exception as err:
            logger.error("Unexpected error loading document '%s': %s", document_id, err)
            return DocumentExtractionResult(
                extraction=None,
                status=AnalysisStatus.FAILED,
                status_reason=f"Document storage retrieval failed: {err}",
            )

        # Step 2: Invoke DocumentIntelligenceAgent for Factual Extraction
        try:
            payload: GeminiExtractionPayload = self.agent.extract_document_payload(
                file_bytes=file_bytes,
                content_type=metadata.content_type,
                filename=metadata.filename,
            )
        except DocumentIntelligenceAgentError as agent_err:
            logger.error("Agent extraction error for document '%s': %s", document_id, agent_err)
            return DocumentExtractionResult(
                extraction=None,
                status=AnalysisStatus.FAILED,
                status_reason=str(agent_err),
            )
        except Exception as err:
            logger.error("Unexpected error during agent extraction for '%s': %s", document_id, err)
            return DocumentExtractionResult(
                extraction=None,
                status=AnalysisStatus.FAILED,
                status_reason=f"Agent execution failure: {err}",
            )

        # Step 3: Sanitize and Validate Standardized Representations
        payload.dates = self.validate_date_representations(payload.dates)
        payload.amounts = self.validate_financial_representations(payload.amounts)

        # Step 4: Deterministic Python Evaluation of AnalysisStatus based on Confidence Threshold
        confidence = payload.extraction_confidence

        if confidence < 0.0 or confidence > 1.0:
            logger.warning(
                "Document '%s' produced out-of-bounds confidence score (%.2f). Defaulting to FAILED.",
                document_id,
                confidence,
            )
            return DocumentExtractionResult(
                extraction=payload,
                status=AnalysisStatus.FAILED,
                status_reason=f"Out-of-bounds confidence score ({confidence:.2f}). Must be between 0.0 and 1.0.",
            )

        if confidence >= self.confidence_threshold:
            status = AnalysisStatus.SUCCESS
            reason = f"Extraction completed successfully with confidence {confidence:.2f} >= threshold {self.confidence_threshold:.2f}."
            logger.info("Analysis SUCCESS for document '%s' (Confidence: %.2f)", document_id, confidence)
        else:
            status = AnalysisStatus.NEEDS_REVIEW
            reason = f"Extraction confidence ({confidence:.2f}) is below confidence threshold ({self.confidence_threshold:.2f}). Manual review required."
            logger.info("Analysis NEEDS_REVIEW for document '%s' (Confidence: %.2f)", document_id, confidence)

        return DocumentExtractionResult(
            extraction=payload,
            status=status,
            status_reason=reason,
        )
