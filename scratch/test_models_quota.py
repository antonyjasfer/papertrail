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

from app.infrastructure.azure.key_vault_provider import AzureKeyVaultSecretProvider
from google import genai

kv = AzureKeyVaultSecretProvider()
api_key = kv.get_secret("gemini-api-key")
client = genai.Client(api_key=api_key)

models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-3.5-flash"
]

print(f"Testing models with API key: ...{api_key[-6:]}")

for m in models_to_test:
    print(f"\n--- Testing Model: {m} ---")
    try:
        resp = client.models.generate_content(
            model=m,
            contents="Say 'OK' if you can read this.",
        )
        print(f"SUCCESS with {m}: {resp.text.strip()}")
    except Exception as e:
        print(f"FAILED with {m}: {e}")
