import os
import sys
import json

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["AZURE_COSMOS_ENDPOINT"] = "https://papertrailcosmosdev2026.documents.azure.com:443/"
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = "https://papertrailstoragedev2026.blob.core.windows.net/"
os.environ["AZURE_SERVICEBUS_NAMESPACE"] = "papertrail-sb-dev-2026.servicebus.windows.net"
os.environ["AZURE_KEYVAULT_URL"] = "https://papertrail-kv-dev-2026.vault.azure.net/"

sys.path.insert(0, ".")

from app.models.analysis import DocumentExtractionResult, GeminiExtractionPayload, LineItem, AnalysisStatus
from app.models.document import DocumentMetadata
from app.models.forensics import HistoricalContext
from app.forensics.engine import ForensicEngine

ext_payload = GeminiExtractionPayload(
    document_type="invoice",
    vendor="SuperStore",
    customer="Aaron Bergman",
    invoice_number="36259",
    dates=["2012-03-06"],
    amounts=["58.11", "53.82", "17.94", "4.29"],
    line_items=[
        LineItem(
            description="Newell 330 Art, Office Supplies, OFF-AR-5309",
            quantity="3",
            unit_price="17.94",
            amount="53.82"
        )
    ],
    extraction_confidence=0.98
)
ext_result = DocumentExtractionResult(
    extraction=ext_payload,
    status=AnalysisStatus.SUCCESS,
    status_reason="Ready"
)
doc_meta = DocumentMetadata(
    document_id="doc-802dabf7f61b",
    filename="clean_invoice_02.pdf",
    content_type="application/pdf",
    size_bytes=14779,
    storage_bucket="papertrail-documents-dev",
    storage_object="documents/doc-802dabf7f61b/original/clean_invoice_02.pdf",
    checksum="ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"
)
hist_ctx = HistoricalContext(
    existing_invoice_numbers=["36259"],
    existing_checksums=["ea0e878b2b4d949a947b7ed11ecb213d9718446f5e4a774c7646270d2f200e6e"]
)

engine = ForensicEngine()
res = engine.analyze(
    extraction_result=ext_result,
    metadata=doc_meta,
    historical_context=hist_ctx
)

print(f"Findings Count: {res.finding_count}")
for f in res.findings:
    print(f"Finding: code={f.finding_code}, severity={f.severity.value}, title={f.title}")
    print(f"  Description: {f.description}")
    print(f"  Evidence: {f.evidence.observed_value} vs expected {f.evidence.expected_value}")

has_critical = any(f.severity.value == "CRITICAL" for f in res.findings)
print(f"Has Critical Severity: {has_critical}")

