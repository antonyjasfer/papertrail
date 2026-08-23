from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json
from typing import Any, Dict
from pydantic import BaseModel

from app.audit.errors import AuditCanonicalizationError


def canonicalize_datetime(dt: datetime) -> str:
    """Format datetime object into deterministic UTC ISO-8601 string preserving microsecond precision.
    
    Format: YYYY-MM-DDTHH:MM:SS.ffffff+00:00
    Examples:
        2026-08-18T18:46:12.123456+00:00
        2026-08-18T18:46:12.000000+00:00
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _normalize(obj: Any) -> Any:
    """Recursively normalize objects into canonical JSON-serializable primitives."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return _normalize(obj.model_dump())
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in sorted(obj.items(), key=lambda x: str(x[0]))}
    if isinstance(obj, (list, tuple)):
        return [_normalize(item) for item in obj]
    if isinstance(obj, Decimal):
        # Preserve exact string representation of Decimal scale (e.g., "10.00")
        return str(obj)
    if isinstance(obj, datetime):
        return canonicalize_datetime(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # Convert float to deterministic string representation
        return str(Decimal(str(obj)))
    
    # Fallback to string conversion for scalar primitives or raise error if unsupported
    try:
        return str(obj)
    except Exception as err:
        raise AuditCanonicalizationError(type(obj).__name__, str(err)) from err


def canonicalize(obj: Any) -> bytes:
    """Produce deterministic canonical UTF-8 JSON byte payload.
    
    Rules:
    1. Lexicographically sorted dictionary keys.
    2. UTC ISO-8601 datetimes with microsecond precision (.ffffff+00:00).
    3. Exact Decimal string representations.
    4. Enum values.
    5. Zero extraneous whitespace (separators=(',', ':')).
    6. UTF-8 encoded.
    """
    normalized = _normalize(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
