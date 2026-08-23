from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
import re
from typing import List, Optional

from app.models.forensics import ForensicFinding


def parse_decimal(val_str: Optional[str]) -> Optional[Decimal]:
    """Parse string representation of currency or numeric value into Python Decimal.

    Strips currency symbols ('$', '€', '£') and thousand separators (',').
    Returns None if value is None, empty, or unparseable.
    """
    if not val_str or not isinstance(val_str, str):
        return None

    cleaned = val_str.strip()
    # Strip currency symbols and commas
    cleaned = re.sub(r"[^\d.-]", "", cleaned)

    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def quantize_currency(value: Decimal, places: int = 2) -> Decimal:
    """Quantize Decimal value to specified currency decimal places using ROUND_HALF_UP rounding policy.

    This ensures deterministic currency arithmetic comparison.
    """
    exponent = Decimal("10") ** (-places)
    return value.quantize(exponent, rounding=ROUND_HALF_UP)


def parse_iso_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 date string into timezone-aware datetime object.

    Returns None if unparseable.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip()

    # Try standard ISO-8601 parsing
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    # Try datetime.fromisoformat fallback
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def deduplicate_findings(findings: List[ForensicFinding]) -> List[ForensicFinding]:
    """Deduplicate findings based on (rule_id, field_reference, observed_value)."""
    seen = set()
    deduped = []
    for finding in findings:
        field_ref = finding.evidence.field_reference if finding.evidence else None
        obs_val = finding.evidence.observed_value if finding.evidence else None
        key = (finding.rule_id, field_ref, obs_val)

        if key not in seen:
            seen.add(key)
            deduped.append(finding)
    return deduped
