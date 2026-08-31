import urllib.request
import json

url = "https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io/health/ready"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "PaperTrail-Test"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("Status:", resp.status)
        print("Body:", resp.read().decode('utf-8'))
except Exception as e:
    print("Health check error:", e)
