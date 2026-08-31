import os
import sys
import json
import time

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

pdf_path = r"c:\Users\anton\OneDrive\Desktop\papertrail\PaperTrail_Test_Documents\01_clean\clean_invoice_03.pdf"
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

agent = DocumentIntelligenceAgent()

print("Testing Gemini live invocation on clean_invoice_03.pdf...")
start_t = time.time()
try:
    payload = agent.extract_document_payload(pdf_bytes, "application/pdf", filename="clean_invoice_03.pdf")
    elapsed = time.time() - start_t
    print(f"SUCCESS in {elapsed:.2f}s!")
    print("Extracted Payload:")
    print(json.dumps(payload.model_dump(), indent=2, default=str))
except Exception as e:
    elapsed = time.time() - start_t
    print(f"FAILED in {elapsed:.2f}s: {e}")
