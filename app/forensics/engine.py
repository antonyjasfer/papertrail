import logging
from typing import List, Optional

from app.forensics.rules import RULE_REGISTRY, BaseRule
from app.forensics.validators import deduplicate_findings
from app.models.analysis import DocumentExtractionResult
from app.models.document import DocumentMetadata
from app.models.forensics import (
    FindingSeverity,
    ForensicAnalysisResult,
    ForensicContext,
    ForensicFinding,
    HistoricalContext,
    SkippedCheck,
)

logger = logging.getLogger("papertrail.forensics.engine")


class ForensicEngine:
    """Deterministic Forensic Engine for PaperTrail AI.

    Executes purely deterministic Python rules against extraction results, metadata, and read-only
    historical context to produce evidence-backed forensic findings.
    Operates with zero LLM/Gemini dependencies, zero database queries/writes, and zero state machine mutations.
    """

    def __init__(self, rules: Optional[List[BaseRule]] = None):
        self.rules = rules if rules is not None else RULE_REGISTRY

    def analyze(
        self,
        extraction_result: DocumentExtractionResult,
        metadata: Optional[DocumentMetadata] = None,
        historical_context: Optional[HistoricalContext] = None,
        context: Optional[ForensicContext] = None,
    ) -> ForensicAnalysisResult:
        """Execute all registered deterministic forensic rules against inputs and return ForensicAnalysisResult."""
        doc_id = metadata.document_id if metadata else "N/A"
        forensic_context = context or ForensicContext()

        logger.info(
            "Executing Deterministic Forensic Engine for document '%s' (Ref Time: %s)",
            doc_id,
            forensic_context.reference_datetime.isoformat(),
        )

        all_findings: List[ForensicFinding] = []
        all_skipped: List[SkippedCheck] = []
        checks_run: List[str] = []

        for rule in self.rules:
            try:
                findings, skipped = rule.execute(
                    extraction_result=extraction_result,
                    metadata=metadata,
                    historical_context=historical_context,
                    context=forensic_context,
                )
                checks_run.append(f"{rule.RULE_ID}: {rule.NAME}")
                all_findings.extend(findings)
                all_skipped.extend(skipped)
            except Exception as err:
                logger.error("Rule '%s' execution failed: %s", rule.RULE_ID, err)
                all_skipped.append(
                    SkippedCheck(
                        rule_id=rule.RULE_ID,
                        reason=f"Execution error: {err}",
                    )
                )

        # Deduplicate findings
        unique_findings = deduplicate_findings(all_findings)

        # Build evidence summary
        severity_counts = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.HIGH: 0,
            FindingSeverity.MEDIUM: 0,
            FindingSeverity.LOW: 0,
        }
        for f in unique_findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        summary = (
            f"Forensic analysis completed. Identified {len(unique_findings)} finding(s) "
            f"({severity_counts[FindingSeverity.CRITICAL]} CRITICAL, "
            f"{severity_counts[FindingSeverity.HIGH]} HIGH, "
            f"{severity_counts[FindingSeverity.MEDIUM]} MEDIUM, "
            f"{severity_counts[FindingSeverity.LOW]} LOW). "
            f"Executed {len(checks_run)} check(s), skipped {len(all_skipped)} check(s)."
        )

        logger.info("Forensic analysis completed for '%s': %s", doc_id, summary)

        return ForensicAnalysisResult(
            document_id=doc_id,
            findings=unique_findings,
            finding_count=len(unique_findings),
            deterministic_checks_run=checks_run,
            checks_skipped=all_skipped,
            evidence_summary=summary,
        )
