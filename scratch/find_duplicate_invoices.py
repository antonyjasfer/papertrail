import os
import glob
import hashlib
import json
import pypdf

base_dir = "PaperTrail_Test_Documents"
all_pdfs = glob.glob(f"{base_dir}/**/*.pdf", recursive=True)

print(f"Total PDFs found in {base_dir}: {len(all_pdfs)}")

invoices = []

for pdf_path in all_pdfs:
    norm_path = pdf_path.replace("\\", "/")
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        size = len(pdf_bytes)

        # Try to extract text with pypdf
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

        invoices.append({
            "path": norm_path,
            "filename": os.path.basename(norm_path),
            "folder": norm_path.split("/")[1] if len(norm_path.split("/")) > 1 else "",
            "size": size,
            "sha256": sha256,
            "text_sample": text[:200].replace("\n", " "),
            "full_text": text
        })
    except Exception as e:
        invoices.append({
            "path": norm_path,
            "filename": os.path.basename(norm_path),
            "error": str(e)
        })

print(f"Parsed {len(invoices)} PDFs.")

# Check for duplicate SHA256 checksums across files
sha_map = {}
for inv in invoices:
    s = inv.get("sha256")
    if s:
        sha_map.setdefault(s, []).append(inv["path"])

dup_shas = {k: v for k, v in sha_map.items() if len(v) > 1}
print(f"\nExact Checksum Duplicate Pairs ({len(dup_shas)}):")
for s, paths in list(dup_shas.items())[:10]:
    print(f" - SHA {s[:12]}...: {paths}")

# Check for identical filenames across folders
name_map = {}
for inv in invoices:
    fn = inv["filename"]
    name_map.setdefault(fn, []).append(inv["path"])

dup_names = {k: v for k, v in name_map.items() if len(v) > 1}
print(f"\nIdentical Filenames Across Folders ({len(dup_names)}):")
for fn, paths in list(dup_names.items())[:10]:
    print(f" - Filename {fn}: {paths}")

