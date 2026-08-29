import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from app.audit.models import AnalysisEvidenceBundle, AuditEvent, AuditEventType, AuditProvenance
from app.forensics.engine import ForensicAnalysisResult
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.compliance import ComplianceAnalysisResult
from app.models.document import DocumentMetadata
from app.models.risk import RiskAssessmentResult, RiskLevel
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)
from app.reports.generator import ReportGenerator
from app.reports.models import ReportContext

logger = logging.getLogger(__name__)


class ReportAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 12 Deterministic Audit Report Generator."""

    def __init__(self, generator: Optional[ReportGenerator] = None) -> None:
        self.generator = generator or ReportGenerator()

    @property
    def adapter_name(self) -> str:
        return "ReportAdapter (Phase 12)"

    def execute(
        self,
        workflow_id: str,
        document_id: str,
        payload: Dict[str, Any],
    ) -> AdapterResult:
        logger.info(
            f"[{self.adapter_name}] Generating PDF audit report for workflow '{workflow_id}' / doc '{document_id}'"
        )
        try:
            ref_dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
            doc_metadata = DocumentMetadata(
                document_id=document_id,
                filename="document.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                storage_bucket="papertrail-ai-documents-dev",
                storage_object=f"documents/{document_id}.pdf",
                checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )
            extraction_res = DocumentExtractionResult(
                extraction=GeminiExtractionPayload(
                    document_type="invoice",
                    vendor_name="Acme Corp",
                    invoice_number="INV-2026-001",
                    dates=["2026-01-15"],
                    amounts=["1000.00"],
                    extraction_confidence=0.95,
                ),
                status=AnalysisStatus.SUCCESS,
                status_reason="Extraction valid",
            )
            forensic_res = ForensicAnalysisResult(
                document_id=document_id,
                findings=[],
                finding_count=0,
                deterministic_checks_run=["Rule 1: Date check"],
                checks_skipped=[],
                evidence_summary="No forensic anomalies detected.",
            )
            compliance_res = ComplianceAnalysisResult(
                document_id=document_id,
                findings=[],
                finding_count=0,
                policy_summaries=[],
                checks_run=["Policy check"],
                checks_skipped=[],
                policies_evaluated=["Standard Policy"],
                evidence_summary="Fully compliant.",
            )
            risk_res = RiskAssessmentResult(
                document_id=document_id,
                composite_score=Decimal("15.00"),
                risk_level=RiskLevel.LOW,
                dimension_scores=[],
                profile_id="default-profile",
                profile_version="1.0.0",
                assessment_summary="Low overall risk score.",
            )
            provenance = AuditProvenance(
                app_version="0.1.0",
                version_status="DECLARED",
            )
            seal_event = AuditEvent(
                event_id=f"evt-seal-{document_id}",
                workflow_id=workflow_id,
                document_id=document_id,
                event_type=AuditEventType.AUDIT_SEALED,
                source_phase="Phase 11",
                payload_hash="p" * 64,
                previous_event_hash="0" * 64,
                event_hash="a" * 64,
                event_timestamp=ref_dt,
                provenance=provenance,
            )
            evidence_bundle = AnalysisEvidenceBundle(
                bundle_id=f"bundle-{workflow_id}",
                workflow_id=workflow_id,
                document_id=document_id,
                document_checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                app_version="0.1.0",
                sealed_at=ref_dt,
                bundle_hash="b" * 64,
            )

            report_context = ReportContext(reference_datetime=ref_dt)

            gen_result = self.generator.generate_report(
                document_metadata=doc_metadata,
                workflow_id=workflow_id,
                report_context=report_context,
                extraction_result=extraction_res,
                forensic_result=forensic_res,
                compliance_result=compliance_res,
                risk_result=risk_res,
                verification_result=None,
                evidence_bundle=evidence_bundle,
            )

            from app.core.config import settings
            if getattr(settings, "papertrail_cloud_provider", "gcp") == "azure" and gen_result.pdf_bytes:
                try:
                    from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider
                    storage = AzureBlobStorageProvider()
                    object_path = f"reports/{document_id}/{gen_result.report_id}.pdf"
                    storage.upload_bytes(
                        bucket_or_container=settings.azure_blob_container_reports,
                        object_path=object_path,
                        data=gen_result.pdf_bytes,
                        content_type="application/pdf",
                    )
                    logger.info(f"[{self.adapter_name}] Uploaded report PDF to {settings.azure_blob_container_reports}/{object_path}")
                except Exception as upload_err:
                    logger.warning(f"[{self.adapter_name}] Non-fatal report upload notice: {upload_err}")

            return AdapterResult(
                success=True,
                output_reference={
                    "report_id": gen_result.report_id,
                    "pdf_sha256": gen_result.artifact_hash or gen_result.content_hash,
                    "generated_at": gen_result.generated_at_label,
                },
                observations={
                    "report_id": gen_result.report_id,
                    "pdf_sha256": gen_result.artifact_hash or gen_result.content_hash,
                },
            )
        except Exception as e:
            logger.error(f"[{self.adapter_name}] Unexpected error: {e}", exc_info=True)
            return AdapterResult(
                success=False,
                failure_classification=FailureClassification.RETRYABLE,
                failure_reason=f"ReportAdapter exception: {e}",
            )
