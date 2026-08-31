import os
import sys
import json

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

agent = DocumentIntelligenceAgent()

pdf_path = "PaperTrail_Test_Documents/01_clean/clean_invoice_03.pdf"
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

payload = agent.extract_document_payload(pdf_bytes, "application/pdf")
print("EXTRACTED PAYLOAD FOR clean_invoice_03.pdf:")
print(json.dumps(payload.model_dump(), indent=2, default=str))
