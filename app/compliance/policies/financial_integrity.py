from app.models.compliance import (
    ComplianceControl,
    CompliancePolicy,
    ControlApplicability,
    ControlSeverity,
    PolicyStatus,
)

INVOICE_FINANCIAL_INTEGRITY_POLICY = CompliancePolicy(
    policy_id="POL-FIN-001",
    name="Invoice Financial Integrity & Verification Policy",
    version="1.0.0",
    description=(
        "Standard organizational policy governing financial integrity, arithmetic correctness, "
        "uniqueness, metadata validity, and cryptographic provenance for commercial invoices."
    ),
    scope=["invoice", "receipt", "purchase_order", "expense_report"],
    effective_from="2026-01-01T00:00:00Z",
    effective_until=None,
    status=PolicyStatus.ACTIVE,
    jurisdiction_labels=["GLOBAL", "US", "EU"],
    controls=[
        ComplianceControl(
            control_id="C-FIN-001",
            policy_id="POL-FIN-001",
            name="Line Item Arithmetic Integrity Control",
            description="Ensures all invoice line item calculations match forensic arithmetic validation.",
            applicability=ControlApplicability(
                document_types=["invoice", "receipt", "purchase_order"],
                required_extraction_fields=["line_items"],
            ),
            rules=["CR-FIN-001"],
            severity=ControlSeverity.HIGH,
            required_evidence=["line_items", "amounts"],
        ),
        ComplianceControl(
            control_id="C-FIN-002",
            policy_id="POL-FIN-002",
            name="Duplicate Document Verification Control",
            description="Prevents processing of duplicate invoices or payload checksums.",
            applicability=ControlApplicability(
                document_types=["invoice", "purchase_order", "receipt"],
            ),
            rules=["CR-FIN-002"],
            severity=ControlSeverity.CRITICAL,
            required_evidence=["invoice_number", "checksum"],
        ),
        ComplianceControl(
            control_id="C-STR-001",
            policy_id="POL-FIN-001",
            name="Structural Field Completeness Control",
            description="Verifies essential structural header fields exist for the document type.",
            applicability=ControlApplicability(
                document_types=["invoice", "purchase_order", "receipt"],
            ),
            rules=["CR-STR-001"],
            severity=ControlSeverity.MEDIUM,
            required_evidence=["vendor", "customer", "invoice_number"],
        ),
        ComplianceControl(
            control_id="C-TMP-001",
            policy_id="POL-FIN-001",
            name="Temporal Date Validity Control",
            description="Guarantees document dates do not exceed context reference execution timestamp.",
            applicability=ControlApplicability(
                document_types=["invoice", "receipt", "purchase_order", "expense_report"],
            ),
            rules=["CR-TMP-001"],
            severity=ControlSeverity.HIGH,
            required_evidence=["dates"],
        ),
        ComplianceControl(
            control_id="C-MET-001",
            policy_id="POL-FIN-001",
            name="Metadata & Provenance Integrity Control",
            description="Validates storage metadata properties and cryptographic checksum provenance.",
            applicability=ControlApplicability(
                document_types=["invoice", "receipt", "purchase_order", "expense_report"],
            ),
            rules=["CR-MET-001", "CR-PRV-001"],
            severity=ControlSeverity.HIGH,
            required_evidence=["size_bytes", "checksum"],
        ),
        ComplianceControl(
            control_id="C-EXT-001",
            policy_id="POL-FIN-001",
            name="Extraction Quality Confidence Control",
            description="Ensures document intelligence extraction confidence meets policy quality thresholds.",
            applicability=ControlApplicability(
                document_types=["invoice", "receipt", "purchase_order", "expense_report"],
            ),
            rules=["CR-EXT-001"],
            severity=ControlSeverity.MEDIUM,
            required_evidence=["extraction_confidence"],
        ),
    ],
)
