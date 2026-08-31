import os
import sys
import json
import zlib
import re

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("scratch/dns_fix"))
import sitecustomize

os.environ["ENVIRONMENT"] = "development"
os.environ["PAPERTRAIL_CLOUD_PROVIDER"] = "azure"

def decode_pdf(path):
    with open(path, "rb") as f:
        data = f.read()
    
    # Parse all streams
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL)
    decompressed = []
    for s in streams:
        try:
            dec = zlib.decompress(s)
            decompressed.append(dec.decode("latin1", errors="ignore"))
        except Exception:
            pass
    return "\n--- STREAM ---\n".join(decompressed)

print("Decoded clean_invoice_03.pdf:")
print(decode_pdf("PaperTrail_Test_Documents/01_clean/clean_invoice_03.pdf"))
