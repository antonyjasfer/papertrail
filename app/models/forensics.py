from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class FindingCategory(str, Enum):
    """Category classification for deterministic forensic findings."""

    FINANCIAL = "FINANCIAL"
    TEMPORAL = "TEMPORAL"
    STRUCTURAL = "STRUCTURAL"
    DUPLICATE = "DUPLICATE"
    METADATA = "METADATA"
    CONTENT = "CONTENT"


class FindingSeverity(str, Enum):
    """Severity classification for deterministic forensic findings.

    Note: FindingSeverity is a rule-specific indicator and does NOT represent a final risk score.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Evidence(BaseModel):
    """Verifiable and reproducible evidence supporting a forensic finding."""

    observed_value: Optional[str] = None
    expected_value: Optional[str] = None
    calculation: Optional[str] = None
    field_reference: Optional[str] = None
    context_notes: Optional[str] = None


class ForensicFinding(BaseModel):
    """Individual deterministic forensic finding backed by verifiable evidence."""

    finding_code: str  # Unique code e.g. "LINE_ITEM_AMOUNT_MISMATCH"
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    evidence: Evidence
    rule_id: str
    deterministic: bool = True
    requires_review: bool = True


class SkippedCheck(BaseModel):
    """Record of a forensic rule skipped due to missing semantic fields or insufficient evidence."""

    rule_id: str
    reason: str


class HistoricalContext(BaseModel):
    """Read-only historical context payload provided by application layer for duplicate checks."""

    existing_invoice_numbers: List[str] = Field(default_factory=list)
    existing_checksums: List[str] = Field(default_factory=list)
    existing_document_fingerprints: List[str] = Field(default_factory=list)


class ForensicContext(BaseModel):
    """Deterministic context providing reference timestamp and options for forensic rules."""

    reference_datetime: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ForensicAnalysisResult(BaseModel):
    """Analysis result envelope returned by ForensicEngine."""

    document_id: str
    findings: List[ForensicFinding] = Field(default_factory=list)
    finding_count: int = 0
    deterministic_checks_run: List[str] = Field(default_factory=list)
    checks_skipped: List[SkippedCheck] = Field(default_factory=list)
    evidence_summary: Optional[str] = None
