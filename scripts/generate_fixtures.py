from datetime import datetime, timezone
from decimal import Decimal
import json
import os

from app.audit.bundle import build_evidence_bundle
from app.audit.chain import AuditChainBuilder
from app.audit.constants import GENESIS_PREVIOUS_HASH
from app.audit.hashing import compute_payload_hash
from app.audit.models import AuditEventType
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, DocumentType, GeminiExtractionPayload
from app.models.compliance import ComplianceAnalysisResult, ComplianceFinding, ComplianceStatus, ComplianceEvidence
from app.models.document import DocumentMetadata, DocumentStatus
from app.models.forensics import FindingCategory, FindingSeverity, ForensicAnalysisResult, ForensicFinding, Evidence
from app.models.risk import RiskAssessmentResult, RiskLevel

FIXTURES_DIR = os.path.join("tests", "fixtures", "audit")
os.makedirs(FIXTURES_DIR, exist_ok=True)

ts_base = datetime(2026, 8, 18, 12, 0, 0, 0, tzinfo=timezone.utc)
doc_id = "doc-fixture-001"
wf_id = "wf-fixture-001"
checksum = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# 1. Document Metadata
metadata = DocumentMetadata(
    document_id=doc_id,
    filename="invoice.pdf",
    content_type="application/pdf",
    size_bytes=1024,
    storage_bucket="test-bucket",
    storage_object="documents/doc-fixture-001/original/invoice.pdf",
    document_status=DocumentStatus.STORED,
    checksum=checksum,
)

# 2. Extraction Payload
extraction = DocumentExtractionResult(
    extraction=GeminiExtractionPayload(
        document_type=DocumentType.INVOICE,
        title="Invoice #1001",
        amounts=["1000.00"],
        extraction_confidence=0.95,
    ),
    status=AnalysisStatus.SUCCESS,
)

# 3. Forensic Result
forensics = ForensicAnalysisResult(
    document_id=doc_id,
    findings=[
        ForensicFinding(
            finding_code="TEMPORAL_DATE_IN_FUTURE",
            category=FindingCategory.TEMPORAL,
            severity=FindingSeverity.LOW,
            title="Date in Future",
            description="Document date exceeds context reference datetime.",
            evidence=Evidence(observed_value="2027-01-01"),
            rule_id="RULE-TMP-001",
        )
    ],
    finding_count=1,
)

# 4. Compliance Result
compliance = ComplianceAnalysisResult(
    document_id=doc_id,
    findings=[
        ComplianceFinding(
            finding_id="cmp-fnd-0001",
            policy_id="POL-FIN-001",
            policy_version="1.0.0",
            control_id="C-FIN-001",
            rule_id="CR-FIN-001",
            status=ComplianceStatus.PASS,
            evidence=ComplianceEvidence(
                policy_reference="POL-FIN-001 v1.0.0",
                control_reference="C-FIN-001",
                rule_reference="CR-FIN-001",
                evaluation_result="PASS",
                source_phase="Phase 9",
            ),
            description="Line item arithmetic verified.",
        )
    ],
    finding_count=1,
)

# 5. Risk Result
risk = RiskAssessmentResult(
    document_id=doc_id,
    composite_score=Decimal("10.00"),
    risk_level=RiskLevel.LOW,
    profile_id="RP-FIN-001",
    profile_version="1.0.0",
    assessment_summary="Low risk document",
)

# Build Clean Audit Chain
evt1 = AuditChainBuilder.create_genesis_event(metadata, wf_id, ts_base)

evt2 = AuditChainBuilder.create_event(
    doc_id, wf_id, AuditEventType.EXTRACTION_COMPLETED, "Phase 7", extraction, evt1.event_hash, ts_base
)

evt3 = AuditChainBuilder.create_event(
    doc_id, wf_id, AuditEventType.FORENSIC_ANALYSIS_COMPLETED, "Phase 8", forensics, evt2.event_hash, ts_base
)

evt4 = AuditChainBuilder.create_event(
    doc_id, wf_id, AuditEventType.COMPLIANCE_ANALYSIS_COMPLETED, "Phase 9", compliance, evt3.event_hash, ts_base
)

evt5 = AuditChainBuilder.create_event(
    doc_id, wf_id, AuditEventType.RISK_ASSESSMENT_COMPLETED, "Phase 10", risk, evt4.event_hash, ts_base
)

bundle = build_evidence_bundle(metadata, wf_id, extraction, forensics, compliance, risk, ts_base)

evt6 = AuditChainBuilder.create_event(
    doc_id, wf_id, AuditEventType.AUDIT_SEALED, "Phase 11", bundle, evt5.event_hash, ts_base
)

clean_chain = [evt1, evt2, evt3, evt4, evt5, evt6]

# Write clean_audit_chain.json
with open(os.path.join(FIXTURES_DIR, "clean_audit_chain.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in clean_chain], f, indent=2)

# Write tampered_payload.json (tamper evt3 payload_hash)
tampered_payload_chain = [e.model_copy(deep=True) for e in clean_chain]
tampered_payload_chain[2].payload_hash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
with open(os.path.join(FIXTURES_DIR, "tampered_payload.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in tampered_payload_chain], f, indent=2)

# Write tampered_previous_hash.json (tamper evt3 previous_event_hash)
tampered_prev_chain = [e.model_copy(deep=True) for e in clean_chain]
tampered_prev_chain[2].previous_event_hash = "0000000000000000000000000000000000000000000000000000000000000000"
with open(os.path.join(FIXTURES_DIR, "tampered_previous_hash.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in tampered_prev_chain], f, indent=2)

# Write missing_forensic_event.json (omit evt3)
missing_forensic_chain = [evt1, evt2, evt4, evt5, evt6]
with open(os.path.join(FIXTURES_DIR, "missing_forensic_event.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in missing_forensic_chain], f, indent=2)

# Write reordered_events.json (out-of-sequence prev-hash linkage)
evt3_reordered = evt3.model_copy(deep=True)
evt3_reordered.previous_event_hash = evt1.event_hash
reordered_chain = [evt1, evt3_reordered, evt2, evt4, evt5, evt6]
with open(os.path.join(FIXTURES_DIR, "reordered_events.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in reordered_chain], f, indent=2)

# Write duplicate_event.json
duplicate_chain = [evt1, evt2, evt2, evt3, evt4, evt5, evt6]
with open(os.path.join(FIXTURES_DIR, "duplicate_event.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in duplicate_chain], f, indent=2)

# Write conflicting_event.json
conflicting_evt2 = evt2.model_copy(deep=True)
conflicting_evt2.payload_hash = "1111111111111111111111111111111111111111111111111111111111111111"
conflicting_chain = [evt1, evt2, conflicting_evt2, evt3, evt4, evt5, evt6]
with open(os.path.join(FIXTURES_DIR, "conflicting_event.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in conflicting_chain], f, indent=2)

# Write schema_version_mismatch.json
schema_mismatch_chain = [e.model_copy(deep=True) for e in clean_chain]
schema_mismatch_chain[1].schema_version = "9.9.9"
with open(os.path.join(FIXTURES_DIR, "schema_version_mismatch.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in schema_mismatch_chain], f, indent=2)

# Write document_checksum_mismatch.json
doc_mismatch_chain = [e.model_copy(deep=True) for e in clean_chain]
doc_mismatch_chain[0].metadata["checksum"] = "0000000000000000000000000000000000000000000000000000000000000000"
with open(os.path.join(FIXTURES_DIR, "document_checksum_mismatch.json"), "w") as f:
    json.dump([e.model_dump(mode="json") for e in doc_mismatch_chain], f, indent=2)

# Write valid_analysis_bundle.json
with open(os.path.join(FIXTURES_DIR, "valid_analysis_bundle.json"), "w") as f:
    json.dump(bundle.model_dump(mode="json"), f, indent=2)

print("Generated 10 golden audit fixtures successfully.")
