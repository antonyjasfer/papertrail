import logging
from typing import List, Optional

from app.compliance.registry import ComplianceRuleRegistry, PolicyRegistry
from app.models.analysis import DocumentExtractionResult, DocumentType
from app.models.compliance import (
    ComplianceAnalysisResult,
    ComplianceContext,
    ComplianceControl,
    ComplianceEvidence,
    ComplianceFinding,
    ComplianceStatus,
    PolicyEvaluationSummary,
    SkippedComplianceCheck,
)
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicAnalysisResult

logger = logging.getLogger("papertrail.compliance.engine")


class ComplianceEngine:
    """Deterministic Compliance Engine for PaperTrail AI.

    Evaluates structured extraction results, document metadata, and forensic analysis findings against
    versioned organizational compliance policies.

    CRITICAL DETERMINISM RULES:
    1. Zero system clock reads (no datetime.now() or datetime.utcnow()).
    2. Context parameter must be explicitly provided by caller with reference_datetime.
    3. Zero LLM/Gemini dependencies.
    4. Zero database queries or writes.
    5. Zero WorkflowState mutations.
    """

    def __init__(
        self,
        policy_registry: Optional[PolicyRegistry] = None,
        rule_registry: Optional[ComplianceRuleRegistry] = None,
    ):
        self.policy_registry = policy_registry or PolicyRegistry()
        self.rule_registry = rule_registry or ComplianceRuleRegistry()

    def evaluate(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        context: ComplianceContext,
    ) -> ComplianceAnalysisResult:
        """Execute deterministic policy compliance evaluation.

        Raises ValueError if context is missing or reference_datetime is None.
        """
        if context is None or not isinstance(context, ComplianceContext) or context.reference_datetime is None:
            raise ValueError("ComplianceContext with explicit reference_datetime is required for compliance evaluation.")

        doc_id = metadata.document_id if metadata else "N/A"
        doc_type = (
            extraction_result.extraction.document_type
            if extraction_result and extraction_result.extraction
            else DocumentType.UNKNOWN
        )

        logger.info(
            "Evaluating compliance for document '%s' (Type: %s, Ref Time: %s)",
            doc_id,
            doc_type.value,
            context.reference_datetime.isoformat(),
        )

        applicable_policies = self.policy_registry.get_applicable_policies(doc_type, context)

        all_findings: List[ComplianceFinding] = []
        all_skipped: List[SkippedComplianceCheck] = []
        checks_run: List[str] = []
        policies_evaluated: List[str] = []
        policy_summaries: List[PolicyEvaluationSummary] = []

        finding_counter = 0

        for policy in applicable_policies:
            policy_ref = f"{policy.policy_id} v{policy.version}"
            policies_evaluated.append(policy_ref)

            summary = PolicyEvaluationSummary(
                policy_id=policy.policy_id,
                policy_version=policy.version,
            )

            for control in policy.controls:
                # 1. Check Control Applicability
                is_applicable, unapp_reason = self._check_control_applicability(control, doc_type, extraction_result)

                if not is_applicable:
                    summary.controls_not_applicable += 1
                    skipped = SkippedComplianceCheck(
                        policy_id=policy.policy_id,
                        control_id=control.control_id,
                        reason=f"Control not applicable: {unapp_reason}",
                    )
                    all_skipped.append(skipped)

                    # Generate NOT_APPLICABLE finding record for visibility
                    finding_counter += 1
                    evidence = ComplianceEvidence(
                        policy_reference=policy_ref,
                        control_reference=control.control_id,
                        rule_reference="N/A",
                        observed_value=f"doc_type={doc_type.value}",
                        expected_condition=f"Control applicability: {control.applicability.document_types}",
                        evaluation_result=ComplianceStatus.NOT_APPLICABLE.value,
                        source_phase="Phase 9",
                        context_notes=unapp_reason,
                    )
                    all_findings.append(
                        ComplianceFinding(
                            finding_id=f"cmp-fnd-{finding_counter:04d}",
                            policy_id=policy.policy_id,
                            policy_version=policy.version,
                            control_id=control.control_id,
                            rule_id="N/A",
                            status=ComplianceStatus.NOT_APPLICABLE,
                            evidence=evidence,
                            description=f"Control '{control.control_id}' is not applicable to document.",
                        )
                    )
                    continue

                # 2. Resolve rules for control
                rules_to_run = self.rule_registry.get_rules_for_control(control)
                if not rules_to_run:
                    summary.controls_insufficient_evidence += 1
                    all_skipped.append(
                        SkippedComplianceCheck(
                            policy_id=policy.policy_id,
                            control_id=control.control_id,
                            reason=f"No matching rules found in registry for control rules {control.rules}.",
                        )
                    )
                    continue

                summary.controls_evaluated += 1

                # Execute rules for control
                control_passed = True
                control_failed = False
                control_insufficient = False
                control_review = False

                for rule in rules_to_run:
                    try:
                        rule_res = rule.evaluate(
                            extraction_result=extraction_result,
                            metadata=metadata,
                            forensic_result=forensic_result,
                            context=context,
                            control=control,
                            policy_version=policy.version,
                        )
                        checks_run.append(f"{policy.policy_id}:{control.control_id}:{rule.RULE_ID}")

                        finding_counter += 1
                        finding = ComplianceFinding(
                            finding_id=f"cmp-fnd-{finding_counter:04d}",
                            policy_id=policy.policy_id,
                            policy_version=policy.version,
                            control_id=control.control_id,
                            rule_id=rule.RULE_ID,
                            status=rule_res.status,
                            evidence=rule_res.evidence,
                            description=rule_res.description,
                        )
                        all_findings.append(finding)

                        if rule_res.status == ComplianceStatus.FAIL:
                            control_failed = True
                            control_passed = False
                        elif rule_res.status == ComplianceStatus.INSUFFICIENT_EVIDENCE:
                            control_insufficient = True
                            control_passed = False
                        elif rule_res.status == ComplianceStatus.REVIEW:
                            control_review = True
                            control_passed = False

                    except Exception as err:
                        logger.error("Rule '%s' execution failed: %s", rule.RULE_ID, err)
                        all_skipped.append(
                            SkippedComplianceCheck(
                                policy_id=policy.policy_id,
                                control_id=control.control_id,
                                rule_id=rule.RULE_ID,
                                reason=f"Execution exception: {err}",
                            )
                        )
                        control_insufficient = True
                        control_passed = False

                if control_failed:
                    summary.controls_failed += 1
                elif control_insufficient:
                    summary.controls_insufficient_evidence += 1
                elif control_review:
                    summary.controls_review += 1
                elif control_passed:
                    summary.controls_passed += 1

            policy_summaries.append(summary)

        # Build overall evidence summary
        total_findings = len(all_findings)
        total_passed = sum(s.controls_passed for s in policy_summaries)
        total_failed = sum(s.controls_failed for s in policy_summaries)
        total_insufficient = sum(s.controls_insufficient_evidence for s in policy_summaries)

        summary_text = (
            f"Compliance evaluation completed for document '{doc_id}'. "
            f"Evaluated {len(policies_evaluated)} policy/policies across {len(checks_run)} check(s). "
            f"Control Results: {total_passed} PASSED, {total_failed} FAILED, {total_insufficient} INSUFFICIENT_EVIDENCE."
        )

        logger.info(summary_text)

        return ComplianceAnalysisResult(
            document_id=doc_id,
            findings=all_findings,
            finding_count=total_findings,
            policy_summaries=policy_summaries,
            checks_run=checks_run,
            checks_skipped=all_skipped,
            policies_evaluated=policies_evaluated,
            evidence_summary=summary_text,
        )

    def _check_control_applicability(
        self,
        control: ComplianceControl,
        doc_type: DocumentType,
        extraction_result: DocumentExtractionResult,
    ) -> tuple[bool, str]:
        """Check if control applicability conditions match doc_type and extraction payload."""
        app = control.applicability
        doc_type_str = doc_type.value.lower() if isinstance(doc_type, DocumentType) else str(doc_type).lower()

        # Check document types
        if app.document_types:
            allowed_types = [t.lower() for t in app.document_types]
            if doc_type_str not in allowed_types:
                return False, f"Document type '{doc_type_str}' not in control allowed types {app.document_types}."

        # Check required extraction fields
        if app.required_extraction_fields and extraction_result and extraction_result.extraction:
            ext = extraction_result.extraction
            for req_field in app.required_extraction_fields:
                val = getattr(ext, req_field, None)
                if val is None or (isinstance(val, list) and len(val) == 0):
                    return False, f"Required semantic field '{req_field}' is missing or empty on extraction payload."

        return True, ""
