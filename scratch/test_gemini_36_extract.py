import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"
os.environ["GEMINI_MODEL"] = "gemini-3.6-flash"

from app.agents.document_intelligence.agent import DocumentIntelligenceAgent

pdf_path = r"c:\Users\anton\OneDrive\Desktop\papertrail\PaperTrail_Test_Documents\01_clean\clean_invoice_03.pdf"
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

agent = DocumentIntelligenceAgent(model_name="gemini-3.6-flash")

print("Testing genuine Gemini 3.6 Flash extraction on clean_invoice_03.pdf...")
payload = agent.extract_document_payload(pdf_bytes, "application/pdf", filename="clean_invoice_03.pdf")

print("\n--- GENUINE GEMINI 3.6 FLASH EXTRACTION SUCCESS ---")
print(json.dumps(payload.model_dump(), indent=2, default=str))
