from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from app.forensics.validators import parse_decimal, parse_iso_date, quantize_currency
from app.models.analysis import (
    DocumentExtractionResult,
    DocumentType,
    GeminiExtractionPayload,
    LineItem,
)
from app.models.document import DocumentMetadata
from app.models.forensics import (
    Evidence,
    FindingCategory,
    FindingSeverity,
    ForensicContext,
    ForensicFinding,
    HistoricalContext,
    SkippedCheck,
)


class BaseRule:
    """Base class for all deterministic forensic rules."""

    RULE_ID: str = "BASE_RULE"
    CATEGORY: FindingCategory = FindingCategory.STRUCTURAL
    NAME: str = "Base Rule"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        raise NotImplementedError


class LineItemArithmeticRule(BaseRule):
    """R-FIN-001: Verifies line item calculation Decimal(quantity) * Decimal(unit_price) == Decimal(amount)."""

    RULE_ID = "LINE_ITEM_AMOUNT_MISMATCH"
    CATEGORY = FindingCategory.FINANCIAL
    NAME = "Line Item Amount Arithmetic Verification"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not extraction_result.extraction or not extraction_result.extraction.line_items:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Required semantic field 'line_items' is missing or empty.",
                )
            )
            return findings, skipped

        checked_items = 0
        for idx, item in enumerate(extraction_result.extraction.line_items):
            q_dec = parse_decimal(item.quantity)
            u_dec = parse_decimal(item.unit_price)
            a_dec = parse_decimal(item.amount)

            if q_dec is None or u_dec is None or a_dec is None:
                continue

            checked_items += 1

            # Quantize both calculated and observed amounts to 2 decimal places using ROUND_HALF_UP policy
            raw_expected = q_dec * u_dec
            expected_amount = quantize_currency(raw_expected)
            observed_amount = quantize_currency(a_dec)

            if observed_amount != expected_amount:
                evidence = Evidence(
                    observed_value=str(observed_amount),
                    expected_value=str(expected_amount),
                    calculation=f"{q_dec} * {u_dec} = {raw_expected} (quantized: {expected_amount})",
                    field_reference=f"line_items[{idx}].amount",
                    context_notes=f"Line item description: '{item.description or 'N/A'}'",
                )
                finding = ForensicFinding(
                    finding_code="LINE_ITEM_AMOUNT_MISMATCH",
                    category=self.CATEGORY,
                    severity=FindingSeverity.HIGH,
                    title="Line Item Amount Mismatch",
                    description=(
                        f"Line item {idx + 1} calculated amount ({expected_amount}) does not match "
                        f"observed amount ({observed_amount})."
                    ),
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        if checked_items == 0:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Line items present but lack required quantity, unit_price, or amount fields for arithmetic verification.",
                )
            )

        return findings, skipped


class FutureDateRule(BaseRule):
    """R-TMP-001: Flags document dates in the future beyond reference datetime provided in ForensicContext."""

    RULE_ID = "FUTURE_DOCUMENT_DATE"
    CATEGORY = FindingCategory.TEMPORAL
    NAME = "Future Document Date Detection"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not extraction_result.extraction or not extraction_result.extraction.dates:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Required semantic field 'dates' is missing or empty.",
                )
            )
            return findings, skipped

        reference_dt = (
            context.reference_datetime
            if context and context.reference_datetime
            else datetime.now(timezone.utc)
        )

        for idx, date_str in enumerate(extraction_result.extraction.dates):
            parsed_dt = parse_iso_date(date_str)
            if not parsed_dt:
                continue

            if parsed_dt > reference_dt:
                evidence = Evidence(
                    observed_value=date_str,
                    expected_value=f"<= {reference_dt.isoformat()}",
                    field_reference=f"dates[{idx}]",
                    context_notes=f"Document date '{date_str}' exceeds context reference timestamp ({reference_dt.isoformat()}).",
                )
                finding = ForensicFinding(
                    finding_code="FUTURE_DOCUMENT_DATE",
                    category=self.CATEGORY,
                    severity=FindingSeverity.HIGH,
                    title="Future Document Date Detected",
                    description=f"Extracted document date '{date_str}' is set in the future relative to reference time.",
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        return findings, skipped


class InvalidDateFormatRule(BaseRule):
    """R-TMP-002: Validates standard ISO-8601 formatting of extracted date strings."""

    RULE_ID = "INVALID_DATE_FORMAT"
    CATEGORY = FindingCategory.TEMPORAL
    NAME = "ISO Date Format Verification"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not extraction_result.extraction or not extraction_result.extraction.dates:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Required semantic field 'dates' is missing or empty.",
                )
            )
            return findings, skipped

        for idx, date_str in enumerate(extraction_result.extraction.dates):
            parsed_dt = parse_iso_date(date_str)
            if not parsed_dt:
                evidence = Evidence(
                    observed_value=date_str,
                    expected_value="Standard ISO-8601 string (e.g. YYYY-MM-DD)",
                    field_reference=f"dates[{idx}]",
                    context_notes="Extracted date string fails standard ISO-8601 parsing.",
                )
                finding = ForensicFinding(
                    finding_code="INVALID_DATE_FORMAT",
                    category=self.CATEGORY,
                    severity=FindingSeverity.MEDIUM,
                    title="Invalid ISO Date Format",
                    description=f"Date string '{date_str}' is not in valid ISO-8601 format.",
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        return findings, skipped


class DateOrderingRule(BaseRule):
    """R-TMP-003: Validates logical temporal ordering between explicit semantic date fields."""

    RULE_ID = "DATE_ORDER_INVALID"
    CATEGORY = FindingCategory.TEMPORAL
    NAME = "Semantic Date Ordering Verification"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        # Only execute if explicit semantic date fields (e.g. issue_date and due_date) are present
        issue_date_val = getattr(extraction_result.extraction, "issue_date", None)
        due_date_val = getattr(extraction_result.extraction, "due_date", None)

        if not issue_date_val or not due_date_val:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Required semantic date ordering fields ('issue_date', 'due_date') are unavailable.",
                )
            )
            return findings, skipped

        issue_dt = parse_iso_date(issue_date_val)
        due_dt = parse_iso_date(due_date_val)

        if issue_dt and due_dt and due_dt < issue_dt:
            evidence = Evidence(
                observed_value=f"issue_date={issue_date_val}, due_date={due_date_val}",
                expected_value="due_date >= issue_date",
                field_reference="issue_date / due_date",
                context_notes="Document due date is set earlier than issue date.",
            )
            finding = ForensicFinding(
                finding_code="DATE_ORDER_INVALID",
                category=self.CATEGORY,
                severity=FindingSeverity.HIGH,
                title="Invalid Date Temporal Order",
                description=f"Due date '{due_date_val}' occurs before issue date '{issue_date_val}'.",
                evidence=evidence,
                rule_id=self.RULE_ID,
            )
            findings.append(finding)

        return findings, skipped


class MissingRequiredFieldRule(BaseRule):
    """R-STR-001: Verifies presence of document-type structural required fields."""

    RULE_ID = "MISSING_REQUIRED_FIELD"
    CATEGORY = FindingCategory.STRUCTURAL
    NAME = "Missing Structural Field Verification"

    REQUIRED_FIELDS_BY_TYPE = {
        DocumentType.INVOICE: ["invoice_number", "vendor", "customer"],
        DocumentType.PURCHASE_ORDER: ["invoice_number", "vendor", "customer"],
        DocumentType.RECEIPT: ["vendor"],
    }

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not extraction_result.extraction:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="Extraction payload is missing.",
                )
            )
            return findings, skipped

        doc_type = extraction_result.extraction.document_type
        required_fields = self.REQUIRED_FIELDS_BY_TYPE.get(doc_type, [])

        if not required_fields:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason=f"No structural required fields defined for document_type '{doc_type.value}'.",
                )
            )
            return findings, skipped

        for field_name in required_fields:
            field_val = getattr(extraction_result.extraction, field_name, None)
            if not field_val:
                evidence = Evidence(
                    observed_value="null or empty",
                    expected_value="Non-empty string",
                    field_reference=field_name,
                    context_notes=f"Document type '{doc_type.value}' expects non-empty '{field_name}'.",
                )
                finding = ForensicFinding(
                    finding_code="MISSING_REQUIRED_FIELD",
                    category=self.CATEGORY,
                    severity=FindingSeverity.MEDIUM,
                    title="Missing Structural Field",
                    description=f"Required field '{field_name}' is missing for document type '{doc_type.value}'.",
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        return findings, skipped


class MetadataConsistencyRule(BaseRule):
    """R-MET-001: Verifies DocumentMetadata properties against extracted content."""

    RULE_ID = "INVALID_DOCUMENT_METADATA"
    CATEGORY = FindingCategory.METADATA
    NAME = "Metadata Consistency Verification"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not metadata:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="DocumentMetadata parameter was not provided.",
                )
            )
            return findings, skipped

        if metadata.size_bytes == 0:
            evidence = Evidence(
                observed_value="0 bytes",
                expected_value="> 0 bytes",
                field_reference="metadata.size_bytes",
                context_notes="Document artifact file size is 0 bytes.",
            )
            finding = ForensicFinding(
                finding_code="INVALID_DOCUMENT_METADATA",
                category=self.CATEGORY,
                severity=FindingSeverity.HIGH,
                title="Zero Byte Document Size",
                description="Document metadata indicates file size is 0 bytes.",
                evidence=evidence,
                rule_id=self.RULE_ID,
            )
            findings.append(finding)

        if not metadata.checksum:
            evidence = Evidence(
                observed_value="null or empty",
                expected_value="64-character SHA-256 hex string",
                field_reference="metadata.checksum",
                context_notes="Document cryptographic checksum is missing.",
            )
            finding = ForensicFinding(
                finding_code="INVALID_DOCUMENT_METADATA",
                category=self.CATEGORY,
                severity=FindingSeverity.MEDIUM,
                title="Missing Document Checksum",
                description="Document metadata is missing SHA-256 cryptographic checksum.",
                evidence=evidence,
                rule_id=self.RULE_ID,
            )
            findings.append(finding)

        return findings, skipped


class DuplicateIdentifierRule(BaseRule):
    """R-DUP-001: Verifies extracted invoice_number or checksum against HistoricalContext."""

    RULE_ID = "DUPLICATE_IDENTIFIER"
    CATEGORY = FindingCategory.DUPLICATE
    NAME = "Duplicate Identifier Verification"

    def execute(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> Tuple[List[ForensicFinding], List[SkippedCheck]]:
        findings: List[ForensicFinding] = []
        skipped: List[SkippedCheck] = []

        if not historical_context:
            skipped.append(
                SkippedCheck(
                    rule_id=self.RULE_ID,
                    reason="HistoricalContext parameter was not provided.",
                )
            )
            return findings, skipped

        # Check duplicate invoice number
        if extraction_result.extraction and extraction_result.extraction.invoice_number:
            inv_num = extraction_result.extraction.invoice_number
            if inv_num in historical_context.existing_invoice_numbers:
                evidence = Evidence(
                    observed_value=inv_num,
                    expected_value="Unique invoice_number",
                    field_reference="extraction.invoice_number",
                    context_notes="Extracted invoice number exists in historical context records.",
                )
                finding = ForensicFinding(
                    finding_code="DUPLICATE_IDENTIFIER",
                    category=self.CATEGORY,
                    severity=FindingSeverity.CRITICAL,
                    title="Duplicate Invoice Number Detected",
                    description=f"Invoice number '{inv_num}' matches a previously processed document.",
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        # Check duplicate SHA-256 checksum
        if metadata and metadata.checksum:
            if metadata.checksum in historical_context.existing_checksums:
                evidence = Evidence(
                    observed_value=metadata.checksum,
                    expected_value="Unique SHA-256 checksum",
                    field_reference="metadata.checksum",
                    context_notes="Document cryptographic checksum matches an existing historical document.",
                )
                finding = ForensicFinding(
                    finding_code="DUPLICATE_IDENTIFIER",
                    category=self.CATEGORY,
                    severity=FindingSeverity.CRITICAL,
                    title="Duplicate Document Payload Checksum",
                    description=f"Document payload checksum '{metadata.checksum[:12]}...' matches a previously processed file.",
                    evidence=evidence,
                    rule_id=self.RULE_ID,
                )
                findings.append(finding)

        return findings, skipped


RULE_REGISTRY: List[BaseRule] = [
    LineItemArithmeticRule(),
    FutureDateRule(),
    InvalidDateFormatRule(),
    DateOrderingRule(),
    MissingRequiredFieldRule(),
    MetadataConsistencyRule(),
    DuplicateIdentifierRule(),
]
