import re
import zlib

with open("PaperTrail_Test_Documents/01_clean/clean_invoice_03.pdf", "rb") as f:
    data = f.read()

print("File size:", len(data))

# Extract all readable ASCII strings
strings = re.findall(rb"[A-Za-z0-9\$\.\,\:\-\/\(\)\ ]{3,}", data)
print("\nDirect ASCII Strings in PDF:")
for s in strings:
    print(" ", s.decode("latin1", errors="ignore"))

# Decompress all flate streams
streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL)
print(f"\nFound {len(streams)} streams")
for idx, s in enumerate(streams):
    try:
        dec = zlib.decompress(s)
        print(f"\n--- Stream {idx} ({len(dec)} bytes) ---")
        dec_strings = re.findall(rb"[A-Za-z0-9\$\.\,\:\-\/\(\)\ ]{3,}", dec)
        for ds in dec_strings:
            print("  ", ds.decode("latin1", errors="ignore"))
    except Exception as e:
        print(f"Stream {idx} decompression failed: {e}")
