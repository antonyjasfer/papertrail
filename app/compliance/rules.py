from typing import List, Optional

from app.models.analysis import DocumentExtractionResult
from app.models.compliance import (
    ComplianceContext,
    ComplianceControl,
    ComplianceEvidence,
    ComplianceRuleResult,
    ComplianceStatus,
)
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicAnalysisResult


class BaseComplianceRule:
    """Base class for all deterministic compliance rules."""

    RULE_ID: str = "BASE_COMPLIANCE_RULE"
    NAME: str = "Base Compliance Rule"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        raise NotImplementedError


class ForensicArithmeticIntegrityRule(BaseComplianceRule):
    """CR-FIN-001: Verifies line item calculation integrity backed by Phase 8 forensic finding."""

    RULE_ID = "CR-FIN-001"
    NAME = "Forensic Line Item Arithmetic Integrity"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"
        target_code = "LINE_ITEM_AMOUNT_MISMATCH"

        if not forensic_result:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="ForensicAnalysisResult provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
                context_notes="ForensicAnalysisResult was not provided.",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Forensic analysis result unavailable for arithmetic check.",
            )

        matching_findings = [f for f in forensic_result.findings if f.finding_code == target_code]
        matching_skipped = [s for s in forensic_result.checks_skipped if s.rule_id == target_code]

        if matching_findings:
            finding = matching_findings[0]
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Forensic finding detected: {finding.title} ({finding.severity.value})",
                expected_condition="Zero LINE_ITEM_AMOUNT_MISMATCH forensic findings",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 8",
                forensic_finding_codes=[target_code],
                context_notes=finding.description,
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Compliance failed due to forensic arithmetic discrepancy: {finding.description}",
            )
        elif matching_skipped:
            skipped_reason = matching_skipped[0].reason
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Forensic check skipped: {skipped_reason}",
                expected_condition="Forensic check LINE_ITEM_AMOUNT_MISMATCH executed successfully",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
                context_notes=f"Forensic check was skipped: {skipped_reason}",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description=f"Insufficient evidence for arithmetic compliance: {skipped_reason}",
            )
        else:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Zero arithmetic findings detected",
                expected_condition="Zero LINE_ITEM_AMOUNT_MISMATCH forensic findings",
                evaluation_result=ComplianceStatus.PASS.value,
                source_phase="Phase 8",
                context_notes="Forensic line item arithmetic check passed with zero anomalies.",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.PASS,
                evidence=evidence,
                description="Line item arithmetic compliance verified.",
            )


class DuplicateDocumentCheckRule(BaseComplianceRule):
    """CR-FIN-002: Verifies document uniqueness backed by Phase 8 duplicate identifier finding."""

    RULE_ID = "CR-FIN-002"
    NAME = "Duplicate Document Verification"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"
        target_code = "DUPLICATE_IDENTIFIER"

        if not forensic_result:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="ForensicAnalysisResult provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
                context_notes="ForensicAnalysisResult was not provided.",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Forensic analysis result unavailable for duplicate check.",
            )

        matching_findings = [f for f in forensic_result.findings if f.finding_code == target_code]
        matching_skipped = [s for s in forensic_result.checks_skipped if s.rule_id == target_code]

        if matching_findings:
            finding = matching_findings[0]
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Duplicate detected: {finding.title}",
                expected_condition="Unique document invoice number and checksum",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 8",
                forensic_finding_codes=[target_code],
                context_notes=finding.description,
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Duplicate document policy violation: {finding.description}",
            )
        elif matching_skipped:
            skipped_reason = matching_skipped[0].reason
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Forensic duplicate check skipped: {skipped_reason}",
                expected_condition="HistoricalContext provided for duplicate verification",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
                context_notes=skipped_reason,
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description=f"Insufficient evidence for duplicate verification: {skipped_reason}",
            )
        else:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Document is unique",
                expected_condition="Zero DUPLICATE_IDENTIFIER forensic findings",
                evaluation_result=ComplianceStatus.PASS.value,
                source_phase="Phase 8",
                context_notes="No duplicate invoice numbers or checksums found in historical context.",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.PASS,
                evidence=evidence,
                description="Document uniqueness verified.",
            )


class RequiredDocumentFieldsRule(BaseComplianceRule):
    """CR-STR-001: Verifies presence of document-type required structural fields."""

    RULE_ID = "CR-STR-001"
    NAME = "Required Structural Field Compliance"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"
        target_code = "MISSING_REQUIRED_FIELD"

        if not forensic_result:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="ForensicAnalysisResult provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Forensic analysis result unavailable for structural field check.",
            )

        matching_findings = [f for f in forensic_result.findings if f.finding_code == target_code]
        matching_skipped = [s for s in forensic_result.checks_skipped if s.rule_id == target_code]

        if matching_findings:
            missing_fields = [f.evidence.field_reference for f in matching_findings if f.evidence]
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Missing fields: {', '.join(filter(None, missing_fields))}",
                expected_condition="All structural required fields present",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 8",
                forensic_finding_codes=[target_code],
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Structural compliance failed due to missing required fields.",
            )
        elif matching_skipped:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Structural check skipped",
                expected_condition="Structural required field check executed",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Insufficient evidence for structural field compliance.",
            )
        else:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="All required fields present",
                expected_condition="All structural required fields present",
                evaluation_result=ComplianceStatus.PASS.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.PASS,
                evidence=evidence,
                description="Structural required fields present and verified.",
            )


class DocumentDateValidityRule(BaseComplianceRule):
    """CR-TMP-001: Verifies document dates do not exceed reference_datetime."""

    RULE_ID = "CR-TMP-001"
    NAME = "Document Temporal Date Validity"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"
        target_code = "FUTURE_DOCUMENT_DATE"

        if not forensic_result:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="ForensicAnalysisResult provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Forensic analysis result unavailable for date validity check.",
            )

        matching_findings = [f for f in forensic_result.findings if f.finding_code == target_code]
        matching_skipped = [s for s in forensic_result.checks_skipped if s.rule_id == target_code]

        if matching_findings:
            finding = matching_findings[0]
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Future date detected: {finding.evidence.observed_value if finding.evidence else 'N/A'}",
                expected_condition=f"Document date <= reference_datetime ({context.reference_datetime.isoformat()})",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 8",
                forensic_finding_codes=[target_code],
                context_notes=finding.description,
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Temporal compliance failed: {finding.description}",
            )
        elif matching_skipped:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Date check skipped",
                expected_condition="Extracted dates available",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Insufficient evidence for document date validity.",
            )
        else:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="All document dates valid",
                expected_condition=f"Document date <= reference_datetime ({context.reference_datetime.isoformat()})",
                evaluation_result=ComplianceStatus.PASS.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.PASS,
                evidence=evidence,
                description="Document temporal dates verified valid.",
            )


class DocumentMetadataIntegrityRule(BaseComplianceRule):
    """CR-MET-001: Verifies storage document metadata integrity."""

    RULE_ID = "CR-MET-001"
    NAME = "Document Metadata Integrity Compliance"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"
        target_code = "INVALID_DOCUMENT_METADATA"

        if not forensic_result:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="ForensicAnalysisResult provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Forensic analysis result unavailable for metadata check.",
            )

        matching_findings = [f for f in forensic_result.findings if f.finding_code == target_code]
        matching_skipped = [s for s in forensic_result.checks_skipped if s.rule_id == target_code]

        if matching_findings:
            finding = matching_findings[0]
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"Metadata defect: {finding.title}",
                expected_condition="Valid DocumentMetadata (non-zero size, valid checksum)",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 8",
                forensic_finding_codes=[target_code],
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Metadata compliance failed: {finding.description}",
            )
        elif matching_skipped:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Metadata check skipped",
                expected_condition="DocumentMetadata provided",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Insufficient evidence for document metadata integrity.",
            )
        else:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="DocumentMetadata valid",
                expected_condition="Valid DocumentMetadata (non-zero size, valid checksum)",
                evaluation_result=ComplianceStatus.PASS.value,
                source_phase="Phase 8",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.PASS,
                evidence=evidence,
                description="Document metadata integrity verified.",
            )


class ProvenanceChecksumPresenceRule(BaseComplianceRule):
    """CR-PRV-001: Verifies SHA-256 cryptographic checksum presence in document metadata."""

    RULE_ID = "CR-PRV-001"
    NAME = "Cryptographic Provenance Checksum Compliance"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"

        if not metadata:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="DocumentMetadata present",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 5",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="DocumentMetadata unavailable for provenance check.",
            )

        if not metadata.checksum or len(metadata.checksum.strip()) == 0:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="Empty or missing checksum",
                expected_condition="Valid SHA-256 hex string",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 5",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description="Cryptographic provenance checksum missing.",
            )

        evidence = ComplianceEvidence(
            policy_reference=policy_ref,
            control_reference=control.control_id,
            rule_reference=self.RULE_ID,
            observed_value=f"SHA-256: {metadata.checksum[:16]}...",
            expected_condition="Valid SHA-256 hex string",
            evaluation_result=ComplianceStatus.PASS.value,
            source_phase="Phase 5",
        )
        return ComplianceRuleResult(
            rule_id=self.RULE_ID,
            status=ComplianceStatus.PASS,
            evidence=evidence,
            description="Cryptographic checksum provenance verified.",
        )


class ExtractionConfidenceThresholdRule(BaseComplianceRule):
    """CR-EXT-001: Verifies Document Intelligence extraction confidence against policy threshold."""

    RULE_ID = "CR-EXT-001"
    NAME = "Extraction Quality Confidence Compliance"

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
        control: ComplianceControl,
        policy_version: str = "1.0.0",
    ) -> ComplianceRuleResult:
        policy_ref = f"{control.policy_id} v{policy_version}"

        if not extraction_result or not extraction_result.extraction:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value="None",
                expected_condition="DocumentExtractionResult payload present",
                evaluation_result=ComplianceStatus.INSUFFICIENT_EVIDENCE.value,
                source_phase="Phase 7",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.INSUFFICIENT_EVIDENCE,
                evidence=evidence,
                description="Document extraction payload unavailable for confidence check.",
            )

        conf = extraction_result.extraction.extraction_confidence
        # Default policy confidence threshold: 0.70 unless configured
        thresh_str = context.configured_thresholds.get("min_extraction_confidence", "0.70")
        try:
            threshold = float(thresh_str)
        except ValueError:
            threshold = 0.70

        if conf < threshold:
            evidence = ComplianceEvidence(
                policy_reference=policy_ref,
                control_reference=control.control_id,
                rule_reference=self.RULE_ID,
                observed_value=f"confidence={conf:.2f}",
                expected_condition=f"confidence >= {threshold:.2f}",
                evaluation_result=ComplianceStatus.FAIL.value,
                source_phase="Phase 7",
            )
            return ComplianceRuleResult(
                rule_id=self.RULE_ID,
                status=ComplianceStatus.FAIL,
                evidence=evidence,
                description=f"Extraction confidence ({conf:.2f}) below required threshold ({threshold:.2f}).",
            )

        evidence = ComplianceEvidence(
            policy_reference=policy_ref,
            control_reference=control.control_id,
            rule_reference=self.RULE_ID,
            observed_value=f"confidence={conf:.2f}",
            expected_condition=f"confidence >= {threshold:.2f}",
            evaluation_result=ComplianceStatus.PASS.value,
            source_phase="Phase 7",
        )
        return ComplianceRuleResult(
            rule_id=self.RULE_ID,
            status=ComplianceStatus.PASS,
            evidence=evidence,
            description="Extraction confidence meets quality threshold.",
        )


DEFAULT_COMPLIANCE_RULES: List[BaseComplianceRule] = [
    ForensicArithmeticIntegrityRule(),
    DuplicateDocumentCheckRule(),
    RequiredDocumentFieldsRule(),
    DocumentDateValidityRule(),
    DocumentMetadataIntegrityRule(),
    ProvenanceChecksumPresenceRule(),
    ExtractionConfidenceThresholdRule(),
]
