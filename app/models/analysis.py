from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Document classification types supported by PaperTrail AI."""

    INVOICE = "invoice"
    RECEIPT = "receipt"
    CONTRACT = "contract"
    EXPENSE_REPORT = "expense_report"
    PURCHASE_ORDER = "purchase_order"
    OTHER = "other"
    UNKNOWN = "unknown"


class AnalysisStatus(str, Enum):
    """Application-level analysis result status computed deterministically by Python logic."""

    SUCCESS = "SUCCESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class LineItem(BaseModel):
    """Structured line item extracted from document.

    Note: All numerical monetary and quantity fields use precise string representations
    (e.g., "1320.50") to prevent floating-point loss prior to forensic verification.
    """

    description: Optional[str] = None
    quantity: Optional[str] = None
    unit_price: Optional[str] = None
    amount: Optional[str] = None


class GeminiExtractionPayload(BaseModel):
    """Factual structured extraction payload returned by Gemini 3.5 Flash.

    Strictly decoupled from application-level AnalysisStatus, risk, fraud, or compliance decisions.
    """

    document_type: DocumentType = DocumentType.UNKNOWN
    title: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)  # Standardized ISO-8601 strings
    amounts: List[str] = Field(default_factory=list)  # String-formatted monetary decimal values
    currency: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    vendor: Optional[str] = None
    customer: Optional[str] = None
    invoice_number: Optional[str] = None
    description: Optional[str] = None
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentExtractionResult(BaseModel):
    """Application-level result envelope wrapping Gemini extraction payload, status, and status reason."""

    extraction: Optional[GeminiExtractionPayload] = None
    status: AnalysisStatus = AnalysisStatus.FAILED
    status_reason: Optional[str] = None
