import os
import re
import zlib
import glob
from decimal import Decimal
from datetime import datetime

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
    
    return " \n ".join(text_blocks)

parsed_docs = []
invoice_numbers_count = {}

for p in pdf_files:
    text = parse_pdf(p)
    if not text:
        continue
    
    # 1. Invoice Number
    inv_m = re.search(r"INVOICE\s*#?\s*([0-9]+)", text.replace("\n", ""))
    inv_num = inv_m.group(1) if inv_m else None
    if inv_num:
        invoice_numbers_count[inv_num] = invoice_numbers_count.get(inv_num, 0) + 1
    
    # 2. Date
    date_m = re.search(r"Date\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text.replace("\n", " "))
    date_str = date_m.group(1) if date_m else None
    
    # 3. Customer
    cust_m = re.search(r"Billed To\s*:\s*([A-Za-z\s]+?)(?:Invoice|Date|Order|$|\n)", text.replace("\n", " "))
    cust_name = cust_m.group(1).strip() if cust_m else None
    
    # 4. Vendor (Usually SuperStore or in header)
    vendor_m = re.search(r"(SuperStore|Acme|Global|TechCorp)", text, re.IGNORECASE)
    vendor_name = vendor_m.group(1) if vendor_m else "SuperStore"
    
    # 5. Line items & arithmetic
    # Look for Qty, Rate, Amount
    lines_raw = text.split("\n")
    qty_rate_matches = re.findall(r"(\d+)\s*\$\s*([\d\.]+)\s*\$\s*([\d\.]+)", text.replace("\n", " "))
    
    # Also dollar amounts
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
                
    parsed_docs.append({
        "path": p,
        "filename": os.path.basename(p),
        "invoice_number": inv_num,
        "date": date_str,
        "customer": cust_name,
        "vendor": vendor_name,
        "amounts": cleaned_amounts,
        "text": text,
        "qty_rate_matches": qty_rate_matches
    })

print(f"Total PDFs parsed: {len(parsed_docs)}")

# Let's find documents with multiple anomalies:
multi_anomaly_candidates = []

for doc in parsed_docs:
    anomalies = []
    
    # Anomaly 1: Missing or weird invoice number
    if not doc["invoice_number"]:
        anomalies.append("MISSING_INVOICE_NUMBER")
        
    # Anomaly 2: Date checks
    if doc["date"]:
        try:
            dt = datetime.strptime(doc["date"], "%Y-%m-%d")
            # If future date beyond 2026-08-31
            if dt > datetime(2026, 8, 31):
                anomalies.append(f"FUTURE_DATE: {doc['date']}")
            # If date is unusual or 0000 or year > 2026
            if dt.year > 2026 or dt.year < 2000:
                anomalies.append(f"UNUSUAL_YEAR: {doc['date']}")
        except Exception as e:
            anomalies.append(f"INVALID_DATE_FORMAT: {doc['date']}")
    else:
        anomalies.append("MISSING_DATE")
        
    # Anomaly 3: Line item arithmetic mismatch
    for q_str, r_str, a_str in doc["qty_rate_matches"]:
        try:
            q = Decimal(q_str)
            r = Decimal(r_str)
            a = Decimal(a_str)
            if q * r != a:
                diff = abs((q * r) - a)
                anomalies.append(f"LINE_ARITHMETIC_MISMATCH: {q} * {r} = {q*r} vs stated {a} (diff: {diff})")
        except Exception:
            pass

    # Anomaly 4: Table totals arithmetic mismatch
    # In SuperStore format, amounts usually: line_rate, line_amount, subtotal, discount, shipping, total
    # If subtotal, discount, shipping, total are present
    if len(doc["amounts"]) >= 5:
        # Check subtotal - discount + shipping == total
        # Often: [unit_price, line_total, subtotal, discount, shipping, total]
        line_tot = doc["amounts"][1]
        subtot = doc["amounts"][2]
        disc = doc["amounts"][3]
        ship = doc["amounts"][4]
        tot = doc["amounts"][5] if len(doc["amounts"]) > 5 else doc["amounts"][-1]
        
        expected_tot = subtot - disc + ship
        if expected_tot != tot:
            diff = abs(expected_tot - tot)
            if diff > Decimal("0.01"):
                anomalies.append(f"TOTAL_ARITHMETIC_MISMATCH: subtotal {subtot} - disc {disc} + ship {ship} = {expected_tot} vs total {tot} (diff: {diff})")

    # Anomaly 5: Duplicate invoice number in dataset
    if doc["invoice_number"] and invoice_numbers_count.get(doc["invoice_number"], 0) > 1:
        anomalies.append(f"DUPLICATE_INVOICE_NUMBER_IN_DATASET: {doc['invoice_number']} (appears {invoice_numbers_count[doc['invoice_number']]} times)")

    # Anomaly 6: Zero or negative or extreme amount
    for amt in doc["amounts"]:
        if amt <= Decimal("0.00"):
            anomalies.append(f"ZERO_OR_NEGATIVE_AMOUNT: {amt}")
        if amt > Decimal("50000.00"):
            anomalies.append(f"EXTREME_AMOUNT: {amt}")

    # Anomaly 7: Customer name check
    if not doc["customer"] or len(doc["customer"]) < 2:
        anomalies.append(f"MISSING_OR_SHORT_CUSTOMER: '{doc['customer']}'")

    if len(anomalies) >= 2:
        multi_anomaly_candidates.append({
            "filename": doc["filename"],
            "invoice_number": doc["invoice_number"],
            "date": doc["date"],
            "customer": doc["customer"],
            "vendor": doc["vendor"],
            "anomalies": anomalies,
            "text_snippet": doc["text"][:300].replace("\n", " ")
        })

print(f"\nFound {len(multi_anomaly_candidates)} candidates with MULTIPLE anomalies (>= 2):\n")
for c in multi_anomaly_candidates[:20]:
    print("----------------------------------------------------------------------")
    print(f"File: {c['filename']} | Invoice: {c['invoice_number']} | Date: {c['date']} | Cust: {c['customer']}")
    print(f"Anomalies ({len(c['anomalies'])}):")
    for a in c["anomalies"]:
        print(f"  - {a}")
