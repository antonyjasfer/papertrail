import os
import sys
import json
from decimal import Decimal
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["AZURE_COSMOS_ENDPOINT"] = "https://papertrailcosmosdev2026.documents.azure.com:443/"
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = "https://papertrailstoragedev2026.blob.core.windows.net/"
os.environ["AZURE_SERVICEBUS_NAMESPACE"] = "papertrail-sb-dev-2026.servicebus.windows.net"
os.environ["AZURE_KEYVAULT_URL"] = "https://papertrail-kv-dev-2026.vault.azure.net/"

from app.agents.document_intelligence.agent import DocumentIntelligenceAgent
from app.forensics.engine import ForensicEngine
from app.compliance.engine import ComplianceEngine
from app.compliance.registry import PolicyRegistry, ComplianceRuleRegistry
from app.compliance.policies.financial_integrity import INVOICE_FINANCIAL_INTEGRITY_POLICY
from app.risk.engine import RiskAssessmentEngine
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, DocumentType
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicContext, HistoricalContext
from app.models.compliance import ComplianceContext
from app.models.risk import RiskContext

agent = DocumentIntelligenceAgent()
forensic_engine = ForensicEngine()
policy_reg = PolicyRegistry(load_defaults=True)
rule_reg = ComplianceRuleRegistry(load_defaults=True)
compliance_evaluator = ComplianceEngine(policy_registry=policy_reg, rule_registry=rule_reg)
risk_engine = RiskAssessmentEngine()

test_candidates = [
    "PaperTrail_Test_Documents/01_clean/clean_invoice_03.pdf", # Zero amounts, missing header fields
    "PaperTrail_Test_Documents/01_clean/clean_invoice_09.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_318.pdf", # Test 2 candidate
    "PaperTrail_Test_Documents/01_clean/clean_invoice_01.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_04.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_05.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_06.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_07.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_08.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_10.pdf",
    "PaperTrail_Test_Documents/01_clean/clean_invoice_102.pdf",
]

results = []

for p in test_candidates[:5]:
    print(f"\n==================== EVALUATING: {p} ====================")
    with open(p, "rb") as f:
        pdf_bytes = f.read()
    
    payload = agent.extract_document_payload(pdf_bytes, "application/pdf")
    doc_id = f"doc-test-{os.path.basename(p)}"
    ext_result = DocumentExtractionResult(
        extraction=payload,
        status=AnalysisStatus.SUCCESS,
        status_reason="Test extraction"
    )
    
    metadata = DocumentMetadata(
        document_id=doc_id,
        filename=os.path.basename(p),
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        storage_bucket="papertrail-documents-dev",
        storage_object=f"documents/{doc_id}/{os.path.basename(p)}",
        checksum="testchecksum1234567890abcdef1234567890abcdef1234567890abcdef12345678"
    )
    
    ref_time = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    
    # 1. Forensics
    f_ctx = ForensicContext(reference_datetime=ref_time)
    h_ctx = HistoricalContext(existing_invoice_numbers=[], existing_checksums=[])
    f_res = forensic_engine.analyze(
        extraction_result=ext_result,
        metadata=metadata,
        historical_context=h_ctx,
        context=f_ctx
    )
    
    # 2. Compliance
    c_ctx = ComplianceContext(reference_datetime=ref_time, jurisdiction_label="GLOBAL")
    c_res = compliance_evaluator.evaluate(
        extraction_result=ext_result,
        metadata=metadata,
        forensic_result=f_res,
        context=c_ctx
    )
    
    # 3. Risk
    r_ctx = RiskContext(reference_datetime=ref_time)
    r_res = risk_engine.assess(
        extraction_result=ext_result,
        metadata=metadata,
        forensic_result=f_res,
        compliance_result=c_res,
        context=r_ctx
    )
    
    print("EXTRACTION:")
    print(f"  Invoice: {payload.invoice_number}, Vendor: {payload.vendor}, Customer: {payload.customer}")
    print(f"  Dates: {payload.dates}, Amounts: {payload.amounts}")
    print(f"  Line Items Count: {len(payload.line_items)}")
    
    print("\nFORENSIC FINDINGS:")
    for finding in f_res.findings:
        print(f"  - [{finding.severity.value}] {finding.finding_code}: {finding.title} -> {finding.description}")
    print(f"  Total findings: {len(f_res.findings)}, Skipped checks: {len(f_res.checks_skipped)}")
    
    print("\nCOMPLIANCE FINDINGS:")
    for finding in c_res.findings:
        print(f"  - [{finding.status.value}] Control: {finding.control_id} (Rule: {finding.rule_id}) -> {finding.description}")
    for summary in c_res.policy_summaries:
        print(f"  Policy {summary.policy_id}: passed={summary.controls_passed}, failed={summary.controls_failed}, review={summary.controls_review}")
    
    print("\nRISK ASSESSMENT:")
    print(f"  Composite Score: {r_res.composite_score} | Level: {r_res.risk_level.value} | Review Recommended: {r_res.review_recommended}")
    print(f"  Assessment Summary: {r_res.assessment_summary}")
    for ds in r_res.dimension_scores:
        print(f"    - {ds.dimension_id} ({ds.dimension_name}): score={ds.score}, weight={ds.weight}, status={ds.status.value}")
