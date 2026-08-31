import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

from google import genai

api_key = "AIzaSyCoFOMbB7gsn7aXT3DcGYjdcKYC8Kn_4rM"
client = genai.Client(api_key=api_key)

print("--- Listing models from GenAI client ---")
try:
    for m in client.models.list():
        # Print supported actions
        print(f"Name: {m.name} | Display: {m.display_name}")
except Exception as e:
    print(f"List models failed: {e}")

test_models = [
    "models/gemini-2.5-flash",
    "models/gemini-3.5-flash",
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.6-flash",
    "models/gemini-2.5-pro",
    "models/gemini-3.5-pro"
]

for m in test_models:
    print(f"\n--- Testing: {m} ---")
    try:
        r = client.models.generate_content(
            model=m,
            contents="Say 'OK'",
        )
        print(f"SUCCESS with {m}: {r.text.strip()}")
    except Exception as e:
        print(f"FAILED with {m}: {e}")
