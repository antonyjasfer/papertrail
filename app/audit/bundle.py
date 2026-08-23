from datetime import datetime, timezone
import hashlib
from typing import List, Optional

from app.audit.canonical import canonicalize
from app.audit.hashing import compute_hash, compute_payload_hash
from app.audit.models import AnalysisEvidenceBundle
from app.core.config import settings
from app.models.analysis import DocumentExtractionResult
from app.models.compliance import ComplianceAnalysisResult
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicAnalysisResult
from app.models.risk import RiskAssessmentResult


def compute_bundle_hash(bundle: AnalysisEvidenceBundle) -> str:
    """Compute deterministic SHA-256 bundle hash over canonical representations of evidence components."""
    hash_input = {
        "bundle_id": bundle.bundle_id,
        "document_id": bundle.document_id,
        "workflow_id": bundle.workflow_id,
        "document_checksum": bundle.document_checksum,
        "extraction_payload_hash": bundle.extraction_payload_hash or "",
        "forensic_result_hash": bundle.forensic_result_hash or "",
        "compliance_result_hash": bundle.compliance_result_hash or "",
        "risk_assessment_hash": bundle.risk_assessment_hash or "",
        "policy_ids": sorted(bundle.policy_ids),
        "policy_versions": sorted(bundle.policy_versions),
        "risk_profile_id": bundle.risk_profile_id or "",
        "risk_profile_version": bundle.risk_profile_version or "",
        "app_version": bundle.app_version,
        "version_status": bundle.version_status,
    }
    canonical_bytes = canonicalize(hash_input)
    return compute_hash(canonical_bytes)


def build_evidence_bundle(
    document_metadata: DocumentMetadata,
    workflow_id: str,
    extraction_result: Optional[DocumentExtractionResult] = None,
    forensic_result: Optional[ForensicAnalysisResult] = None,
    compliance_result: Optional[ComplianceAnalysisResult] = None,
    risk_result: Optional[RiskAssessmentResult] = None,
    sealed_at: Optional[datetime] = None,
) -> AnalysisEvidenceBundle:
    """Build and seal an AnalysisEvidenceBundle from prior phase analysis results."""
    doc_id = document_metadata.document_id
    bundle_id = f"bundle-{doc_id}-{workflow_id}"

    ext_hash = compute_payload_hash(extraction_result) if extraction_result else None
    for_hash = compute_payload_hash(forensic_result) if forensic_result else None
    cmp_hash = compute_payload_hash(compliance_result) if compliance_result else None
    rsk_hash = compute_payload_hash(risk_result) if risk_result else None

    policy_ids: List[str] = []
    policy_versions: List[str] = []
    if compliance_result and compliance_result.findings:
        p_ids = set()
        p_vers = set()
        for f in compliance_result.findings:
            p_ids.add(f.policy_id)
            p_vers.add(f.policy_version)
        policy_ids = sorted(list(p_ids))
        policy_versions = sorted(list(p_vers))

    prof_id = risk_result.profile_id if risk_result else None
    prof_ver = risk_result.profile_version if risk_result else None

    ts = sealed_at or datetime.now(timezone.utc)

    bundle = AnalysisEvidenceBundle(
        bundle_id=bundle_id,
        document_id=doc_id,
        workflow_id=workflow_id,
        document_checksum=document_metadata.checksum,
        extraction_payload_hash=ext_hash,
        forensic_result_hash=for_hash,
        compliance_result_hash=cmp_hash,
        risk_assessment_hash=rsk_hash,
        policy_ids=policy_ids,
        policy_versions=policy_versions,
        risk_profile_id=prof_id,
        risk_profile_version=prof_ver,
        app_version=settings.app_version,
        version_status="DECLARED",
        sealed_at=ts,
        bundle_hash="",
    )
    bundle.bundle_hash = compute_bundle_hash(bundle)
    return bundle
