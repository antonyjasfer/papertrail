import os
import re
import zlib
import glob
from collections import defaultdict

def parse_cmap_array(chunk):
    res = {}
    m = re.search(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*\[(.*?)\]", chunk, re.DOTALL)
    if m:
        start = int(m.group(1), 16)
        end = int(m.group(2), 16)
        hex_list = re.findall(r"<([0-9a-fA-F]+)>", m.group(3))
        for idx, h in enumerate(hex_list):
            code = start + idx
            char = bytes.fromhex(h).decode("utf-16be", errors="ignore")
            res[f"{code:04X}"] = char
    return res

def parse_pdf(path):
    with open(path, "rb") as f:
        data = f.read()
    
    cmap_16 = {}
    cmap_21 = {}
    idx16 = data.find(b"16 0 obj")
    if idx16 != -1:
        end16 = data.find(b"endobj", idx16)
        cmap_16 = parse_cmap_array(data[idx16:end16].decode("latin1"))

    idx21 = data.find(b"21 0 obj")
    if idx21 != -1:
        end21 = data.find(b"endobj", idx21)
        cmap_21 = parse_cmap_array(data[idx21:end21].decode("latin1"))

    stream1_m = re.search(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL)
    if not stream1_m:
        return {}
    try:
        dec = zlib.decompress(stream1_m.group(1))
    except Exception:
        return {}

    lines = dec.split(b"\n")
    current_cmap = cmap_16
    
    current_str = []
    text_blocks = []
    
    for l in lines:
        l_str = l.decode("latin1")
        if "/F1 " in l_str or "/F1" in l_str:
            current_cmap = cmap_16
        elif "/F2 " in l_str or "/F2" in l_str:
            current_cmap = cmap_21
        
        if "Tm" in l_str or "Td" in l_str or "T*" in l_str:
            if current_str:
                text_blocks.append("".join(current_str))
                current_str = []
        
        hex_matches = re.findall(r"<([0-9a-fA-F]+)>", l_str)
        for hm in hex_matches:
            for i in range(0, len(hm), 4):
                code = hm[i:i+4].upper()
                current_str.append(current_cmap.get(code, "?"))
                
    if current_str:
        text_blocks.append("".join(current_str))

    full_text = " \n ".join(text_blocks)
    
    # Extract Invoice Number
    inv_m = re.search(r"Invoice\s*#?\s*:\s*(\d+)", full_text, re.IGNORECASE)
    inv_num = inv_m.group(1) if inv_m else None
    
    # Extract Order ID
    order_m = re.search(r"Order\s*ID\s*:\s*([^\n\r]+)", full_text, re.IGNORECASE)
    order_id = order_m.group(1).strip() if order_m else None

    # Extract Total
    tot_m = re.search(r"Total\s*:\s*([0-9,]+\.\d{2})", full_text, re.IGNORECASE)
    total = tot_m.group(1) if tot_m else None

    # Extract Date
    date_m = re.search(r"Invoice\s*Date\s*:\s*(\d{4}-\d{2}-\d{2})", full_text, re.IGNORECASE)
    inv_date = date_m.group(1) if date_m else None

    return {
        "path": path,
        "filename": os.path.basename(path),
        "invoice_number": inv_num,
        "order_id": order_id,
        "total": total,
        "date": inv_date,
        "text_blocks": text_blocks
    }

all_files = sorted(glob.glob("PaperTrail_Test_Documents/01_clean/*.pdf"))
print(f"Scanning {len(all_files)} invoices...")

results = []
for p in all_files:
    r = parse_pdf(p)
    if r.get("invoice_number"):
        results.append(r)

print(f"Successfully extracted invoice numbers from {len(results)} files.")

# Group by invoice number
by_inv = defaultdict(list)
for r in results:
    by_inv[r["invoice_number"]].append(r)

dups_inv = {k: v for k, v in by_inv.items() if len(v) > 1}
print(f"\nFound {len(dups_inv)} duplicate invoice numbers across different files:")
for inv_num, files in dups_inv.items():
    print(f"\nInvoice #{inv_num} appears in {len(files)} files:")
    for f in files:
        print(f"  - File: {f['filename']} | Date: {f['date']} | Order: {f['order_id']} | Total: ${f['total']}")

# Group by Order ID
by_order = defaultdict(list)
for r in results:
    if r.get("order_id"):
        by_order[r["order_id"]].append(r)

dups_order = {k: v for k, v in by_order.items() if len(v) > 1}
print(f"\nFound {len(dups_order)} duplicate Order IDs across different files:")
for oid, files in list(dups_order.items())[:5]:
    print(f"\nOrder ID '{oid}' appears in {len(files)} files:")
    for f in files:
        print(f"  - File: {f['filename']} | Invoice: #{f['invoice_number']} | Total: ${f['total']}")

