import os
import glob
import re
import zlib
from decimal import Decimal

pdf_files = sorted(glob.glob("PaperTrail_Test_Documents/01_clean/*.pdf"))

def parse_cmap(data):
    cmap = {}
    for m in re.finditer(r'<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*\[(.*?)\]', data, re.DOTALL):
        start = int(m.group(1), 16)
        hexes = re.findall(r'<([0-9a-fA-F]+)>', m.group(3))
        for idx, h in enumerate(hexes):
            code = start + idx
            char = bytes.fromhex(h).decode('utf-16be', errors='ignore')
            cmap[f'{code:04X}'] = char
    return cmap

def decode(path):
    with open(path, 'rb') as f:
        data = f.read()
    cmap = parse_cmap(data.decode('latin1', errors='ignore'))
    stream_m = re.search(rb'stream\r?\n(.*?)\r?\nendstream', data, re.DOTALL)
    if not stream_m: return ''
    try:
        dec = zlib.decompress(stream_m.group(1))
    except: return ''
    lines = []
    for l in dec.split(b'\n'):
        if b'Tj' in l or b'TJ' in l:
            hexes = re.findall(r'<([0-9a-fA-F]+)>', l.decode('latin1', errors='ignore'))
            t = ''.join(cmap.get(h.upper(), '') for h in hexes)
            if t.strip():
                lines.append(t.strip())
    return '\n'.join(lines)

all_invoices = []
for p in pdf_files:
    text = decode(p)
    all_invoices.append({"path": p, "name": os.path.basename(p), "text": text, "size": os.path.getsize(p)})

print(f"Loaded {len(all_invoices)} invoices")

# 1. Inspect the 15 files with size 9834
print("\n--- 15 Files with size 9834 bytes ---")
for inv in all_invoices:
    if inv["size"] == 9834:
        print(f"File: {inv['name']} | Lines: {len(inv['text'].splitlines())} | Text snippet: {inv['text'][:100].replace(chr(10), ' ')}")

# 2. Check for future dates / years
print("\n--- Checking dates across all invoices ---")
dates_found = set()
future_dates = []
for inv in all_invoices:
    matches = re.findall(r'\b(20\d\d[-/]\d\d[-/]\d\d|\w+ \d+, \d{4})\b', inv["text"])
    for d in matches:
        dates_found.add(d)
        if "2027" in d or "2028" in d or "2029" in d or "2030" in d:
            future_dates.append((inv["name"], d))

print(f"Unique dates found: {len(dates_found)}")
print(f"Future dates (>2026): {future_dates}")

# 3. Check for arithmetic mismatches across all standard invoices
# Let's inspect invoices where line items have arithmetic discrepancies
arithmetic_issues = []
for inv in all_invoices:
    # Look for quantity * unit price vs total
    # Pattern in text: lines might contain numbers
    nums = re.findall(r'\$?\b(\d+\.\d{2})\b', inv["text"])
    integers = re.findall(r'\b([1-9]\d?)\b', inv["text"])
    # Let's check for any explicit arithmetic anomalies
