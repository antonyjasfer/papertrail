import hashlib
from typing import List

# Declared implementation versions for upstream engines
FORENSIC_ENGINE_VERSION: str = "1.0.0"
COMPLIANCE_ENGINE_VERSION: str = "1.0.0"
RISK_ENGINE_VERSION: str = "1.0.0"

# Audit layer versions & cryptographic markers
AUDIT_SCHEMA_VERSION: str = "1.0.0"
GENESIS_MARKER: str = "GENESIS:papertrail-ai:v1"
GENESIS_PREVIOUS_HASH: str = hashlib.sha256(GENESIS_MARKER.encode("utf-8")).hexdigest()
HASH_ALGORITHM: str = "SHA-256"

# Canonical happiness-path event sequence for complete workflow analysis
EXPECTED_AUDIT_EVENT_SEQUENCE: List[str] = [
    "DOCUMENT_REGISTERED",
    "EXTRACTION_COMPLETED",
    "FORENSIC_ANALYSIS_COMPLETED",
    "COMPLIANCE_ANALYSIS_COMPLETED",
    "RISK_ASSESSMENT_COMPLETED",
    "AUDIT_SEALED",
]
