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

from app.infrastructure.azure.key_vault_provider import AzureKeyVaultSecretProvider
from google import genai

kv = AzureKeyVaultSecretProvider()
api_key = kv.get_secret("gemini-api-key")
client = genai.Client(api_key=api_key)

print("Listing all available models from Google API...")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(f"Model: {m.name} | Display: {m.display_name}")

candidates = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-pro", "gemini-3.5-pro"]
for c in candidates:
    print(f"\n--- Testing Candidate: {c} ---")
    try:
        resp = client.models.generate_content(
            model=c,
            contents="Say 'OK'",
        )
        print(f"SUCCESS with {c}: {resp.text.strip()}")
    except Exception as e:
        print(f"FAILED with {c}: {e}")
