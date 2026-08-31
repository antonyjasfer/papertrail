import os
import re
import zlib
import glob
from collections import defaultdict
from decimal import Decimal

pdf_files = sorted(glob.glob("PaperTrail_Test_Documents/01_clean/*.pdf"))

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
        return ""
    try:
        dec = zlib.decompress(stream1_m.group(1))
    except Exception:
        return ""

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
        
        if "Tj" in l_str or "TJ" in l_str:
            hexes = re.findall(r"<([0-9a-fA-F]+)>", l_str)
            text = "".join(current_cmap.get(h.upper(), "") for h in hexes)
            if text:
                current_str.append(text)
                
    if current_str:
        text_blocks.append("".join(current_str))
    
    return "\n".join(text_blocks)

invoices = []
for p in pdf_files:
    text = parse_pdf(p)
    if not text:
        continue
    # Search for invoice number after "INVOICE #" or "Invoice #"
    inv_m = re.search(r"INVOICE\s*#?\s*([0-9]+)", text.replace("\n", ""))
    inv_num = inv_m.group(1) if inv_m else "Unknown"
    
    # Search for date
    date_m = re.search(r"Invoice\s*Date\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text.replace("\n", " "))
    inv_date = date_m.group(1) if date_m else "Unknown"
    
    # Search for total
    tot_m = re.search(r"Total\s*:\s*\$?\s*([0-9,]+\.\d{2})", text.replace("\n", " "))
    tot = tot_m.group(1) if tot_m else "Unknown"

    invoices.append({
        "path": p,
        "filename": os.path.basename(p),
        "invoice_number": inv_num,
        "date": inv_date,
        "total": tot,
        "text": text[:300].replace("\n", " ")
    })

print(f"Parsed {len(invoices)} invoices.")

by_num = defaultdict(list)
for inv in invoices:
    by_num[inv["invoice_number"]].append(inv)

dups = {k: v for k, v in by_num.items() if len(v) > 1 and k != "Unknown"}
print(f"\nFound {len(dups)} duplicate invoice numbers:")
for inv_num, flist in list(dups.items())[:10]:
    print(f"\nInvoice #{inv_num} ({len(flist)} occurrences):")
    for f in flist:
        print(f"  File: {f['filename']} | Date: {f['date']} | Total: ${f['total']}")
