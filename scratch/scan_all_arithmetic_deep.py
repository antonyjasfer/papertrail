import os
import glob
import re
import zlib
from decimal import Decimal

pdf_files = sorted(glob.glob("PaperTrail_Test_Documents/01_clean/*.pdf"))

def parse_cmap_array(chunk):
    res = {}
    m = re.search(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*\[(.*?)\]", chunk, re.DOTALL)
    if m:
        start = int(m.group(1), 16)
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
    
    return " \n ".join(text_blocks)

candidates = []

for p in pdf_files:
    if os.path.getsize(p) == 9834:
        continue
    text = parse_pdf(p)
    if not text:
        continue

    # Extract all dollar amounts
    raw_dollars = re.findall(r"\$\s*([\d\s\n\,\.]+)", text)
    cleaned_amounts = []
    for d in raw_dollars:
        c = d.replace("\n", "").replace(" ", "").replace(",", "")
        m = re.match(r"^(\d+\.\d{2})", c)
        if m:
            try:
                cleaned_amounts.append(Decimal(m.group(1)))
            except Exception:
                pass

    # Extract integer quantities
    # In the PDF, line items have description, quantity, unit price, amount
    # Let's extract invoice number
    inv_m = re.search(r"INVOICE\s*#?\s*([0-9]+)", text.replace("\n", ""))
    inv_num = inv_m.group(1) if inv_m else "Unknown"

    cust_m = re.search(r"Billed To\s*:\s*([A-Za-z\s]+?)(?:Invoice|Date|Order|$|\n)", text.replace("\n", " "))
    cust = cust_m.group(1).strip() if cust_m else "Unknown"

    date_m = re.search(r"Date\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text.replace("\n", " "))
    dt = date_m.group(1) if date_m else "Unknown"

    # Check for arithmetic discrepancies in amounts:
    # Typically: cleaned_amounts = [unit_price, line_total, subtotal, shipping, total] or [unit_price, line_total, subtotal, discount, shipping, total]
    # Let's check for any quantity where q * unit_price != line_total
    # Search for all integer quantities from 1 to 50
    item_discrepancies = []
    if len(cleaned_amounts) >= 2:
        unit_price = cleaned_amounts[0]
        stated_line_total = cleaned_amounts[1]
        
        # Let's search text for the quantity
        q_matches = re.findall(r"\b([1-9]\d?)\b", text)
        for q_str in q_matches:
            q = Decimal(q_str)
            if q > 1 and q < 50:
                expected = (q * unit_price).quantize(Decimal("0.01"))
                if expected == stated_line_total:
                    # Perfect match, so quantity is q
                    break
                elif abs(expected - stated_line_total) <= Decimal("1.00") and expected != stated_line_total:
                    item_discrepancies.append((q, unit_price, stated_line_total, expected, abs(expected - stated_line_total)))

    if item_discrepancies:
        candidates.append({
            "file": os.path.basename(p),
            "invoice": inv_num,
            "customer": cust,
            "date": dt,
            "discrepancies": item_discrepancies,
            "amounts": cleaned_amounts
        })

print(f"Total arithmetic candidates found: {len(candidates)}")
for c in candidates:
    print(f"File: {c['file']} | Inv: {c['invoice']} | Cust: {c['customer']} | Date: {c['date']}")
    for d in c["discrepancies"]:
        print(f"   Qty: {d[0]}, Rate: {d[1]}, Stated: {d[2]}, Expected: {d[3]}, Diff: {d[4]}")
