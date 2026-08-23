from decimal import Decimal
import logging
from typing import List, Optional, Tuple

from app.models.analysis import DocumentExtractionResult
from app.models.compliance import ComplianceAnalysisResult, ComplianceStatus
from app.models.document import DocumentMetadata
from app.models.forensics import FindingSeverity, ForensicAnalysisResult
from app.models.risk import (
    DimensionScore,
    DimensionStatus,
    RiskEvidence,
    RiskFactor,
    RiskProfile,
    SkippedRiskCheck,
    TraceStep,
)

logger = logging.getLogger("papertrail.risk.scorers")

FORENSIC_SEVERITY_WEIGHTS = {
    FindingSeverity.CRITICAL: Decimal("100.00"),
    FindingSeverity.HIGH: Decimal("70.00"),
    FindingSeverity.MEDIUM: Decimal("40.00"),
    FindingSeverity.LOW: Decimal("15.00"),
}

COMPLIANCE_STATUS_WEIGHTS = {
    ComplianceStatus.FAIL: Decimal("100.00"),
    ComplianceStatus.REVIEW: Decimal("50.00"),
    ComplianceStatus.INSUFFICIENT_EVIDENCE: Decimal("30.00"),
    ComplianceStatus.PASS: Decimal("0.00"),
    ComplianceStatus.NOT_APPLICABLE: Decimal("0.00"),
}


def parse_all_risk_factors(
    extraction_result: Optional[DocumentExtractionResult],
    metadata: Optional[DocumentMetadata],
    forensic_result: Optional[ForensicAnalysisResult],
    compliance_result: Optional[ComplianceAnalysisResult],
) -> List[RiskFactor]:
    """Parse structured risk factors from prior phase outputs for evidence lineage aggregation."""
    factors: List[RiskFactor] = []

    # 1. Parse Forensic Factors (Phase 8)
    if forensic_result and forensic_result.findings:
        for idx, f in enumerate(forensic_result.findings):
            field_ref = f.evidence.field_reference if f.evidence else "N/A"
            obs_val = f.evidence.observed_value if f.evidence else "N/A"
            lineage_key = f"evidence:{f.finding_code}:{field_ref}:{obs_val}"
            raw_val = FORENSIC_SEVERITY_WEIGHTS.get(f.severity, Decimal("0.00"))

            factors.append(
                RiskFactor(
                    factor_id=f"RF-FOR-{f.finding_code}-{idx + 1:02d}",
                    category="FORENSIC",
                    source_phase="Phase 8",
                    source_reference=f.finding_code,
                    lineage_key=lineage_key,
                    severity_label=f.severity.value,
                    raw_value=raw_val,
                    normalized_value=raw_val,
                    evidence_notes=f"Forensic finding '{f.title}' ({f.severity.value}): {f.description}",
                )
            )

    # 2. Parse Compliance Factors (Phase 9)
    if compliance_result and compliance_result.findings:
        for idx, cf in enumerate(compliance_result.findings):
            if cf.status in (ComplianceStatus.PASS, ComplianceStatus.NOT_APPLICABLE):
                continue

            forensic_code = (
                cf.evidence.forensic_finding_codes[0]
                if cf.evidence and cf.evidence.forensic_finding_codes
                else None
            )
            obs_val = cf.evidence.observed_value if cf.evidence else "N/A"

            if forensic_code:
                # Share lineage key with forensic finding if applicable
                lineage_key = f"evidence:{forensic_code}:{cf.evidence.control_reference}:{obs_val}"
            else:
                lineage_key = f"evidence:{cf.policy_id}:{cf.control_id}:{cf.rule_id}:{obs_val}"

            raw_val = COMPLIANCE_STATUS_WEIGHTS.get(cf.status, Decimal("0.00"))

            factors.append(
                RiskFactor(
                    factor_id=f"RF-CMP-{cf.control_id}-{idx + 1:02d}",
                    category="COMPLIANCE",
                    source_phase="Phase 9",
                    source_reference=f"{cf.policy_id}:{cf.control_id}",
                    lineage_key=lineage_key,
                    severity_label=cf.status.value,
                    raw_value=raw_val,
                    normalized_value=raw_val,
                    evidence_notes=f"Compliance control '{cf.control_id}' status {cf.status.value}: {cf.description}",
                )
            )

    return factors


def score_forensic_dimension(
    factors: List[RiskFactor],
    forensic_result: Optional[ForensicAnalysisResult],
    profile: RiskProfile,
) -> Tuple[DimensionScore, Optional[SkippedRiskCheck]]:
    """Score DIM-FOR (Forensic Anomaly Risk) using Decimal arithmetic."""
    dim_weight = profile.dimension_weights.get("DIM-FOR", Decimal("0.30"))

    if forensic_result is None:
        skipped = SkippedRiskCheck(
            dimension_id="DIM-FOR",
            reason="ForensicAnalysisResult is None. Forensic risk could not be evaluated.",
        )
        evidence = RiskEvidence(
            dimension_id="DIM-FOR",
            dimension_name="Forensic Anomaly Risk",
            raw_score=Decimal("0.00"),
            weighted_contribution=Decimal("0.00"),
            weight=dim_weight,
            contributing_factors=[],
            source_phase="Phase 8",
            scoring_rationale="ForensicAnalysisResult unavailable. Status set to INSUFFICIENT_DATA.",
        )
        score = DimensionScore(
            dimension_id="DIM-FOR",
            dimension_name="Forensic Anomaly Risk",
            score=Decimal("0.00"),
            status=DimensionStatus.INSUFFICIENT_DATA,
            weight=dim_weight,
            reweighted_weight=dim_weight,
            weighted_contribution=Decimal("0.00"),
            evidence=evidence,
        )
        return score, skipped

    for_factors = [f for f in factors if f.category == "FORENSIC"]
    raw_sum = sum(f.normalized_value for f in for_factors) if for_factors else Decimal("0.00")
    capped_score = min(raw_sum, Decimal("100.00"))

    evidence = RiskEvidence(
        dimension_id="DIM-FOR",
        dimension_name="Forensic Anomaly Risk",
        raw_score=capped_score,
        weighted_contribution=Decimal("0.00"),  # Computed during engine composite aggregation
        weight=dim_weight,
        contributing_factors=[f.factor_id for f in for_factors if f.normalized_value > Decimal("0.00")],
        source_phase="Phase 8",
        scoring_rationale=f"Evaluated {len(for_factors)} forensic risk factor(s). Sum raw value: {raw_sum}, capped: {capped_score}.",
    )
    score = DimensionScore(
        dimension_id="DIM-FOR",
        dimension_name="Forensic Anomaly Risk",
        score=capped_score,
        status=DimensionStatus.AVAILABLE,
        weight=dim_weight,
        reweighted_weight=dim_weight,
        weighted_contribution=Decimal("0.00"),
        evidence=evidence,
    )
    return score, None


def score_compliance_dimension(
    factors: List[RiskFactor],
    compliance_result: Optional[ComplianceAnalysisResult],
    profile: RiskProfile,
) -> Tuple[DimensionScore, Optional[SkippedRiskCheck]]:
    """Score DIM-CMP (Compliance Violation Risk) using Decimal arithmetic."""
    dim_weight = profile.dimension_weights.get("DIM-CMP", Decimal("0.30"))

    if compliance_result is None:
        skipped = SkippedRiskCheck(
            dimension_id="DIM-CMP",
            reason="ComplianceAnalysisResult is None. Compliance risk could not be evaluated.",
        )
        evidence = RiskEvidence(
            dimension_id="DIM-CMP",
            dimension_name="Compliance Violation Risk",
            raw_score=Decimal("0.00"),
            weighted_contribution=Decimal("0.00"),
            weight=dim_weight,
            contributing_factors=[],
            source_phase="Phase 9",
            scoring_rationale="ComplianceAnalysisResult unavailable. Status set to INSUFFICIENT_DATA.",
        )
        score = DimensionScore(
            dimension_id="DIM-CMP",
            dimension_name="Compliance Violation Risk",
            score=Decimal("0.00"),
            status=DimensionStatus.INSUFFICIENT_DATA,
            weight=dim_weight,
            reweighted_weight=dim_weight,
            weighted_contribution=Decimal("0.00"),
            evidence=evidence,
        )
        return score, skipped

    cmp_factors = [f for f in factors if f.category == "COMPLIANCE"]
    raw_sum = sum(f.normalized_value for f in cmp_factors) if cmp_factors else Decimal("0.00")
    capped_score = min(raw_sum, Decimal("100.00"))

    evidence = RiskEvidence(
        dimension_id="DIM-CMP",
        dimension_name="Compliance Violation Risk",
        raw_score=capped_score,
        weighted_contribution=Decimal("0.00"),
        weight=dim_weight,
        contributing_factors=[f.factor_id for f in cmp_factors if f.normalized_value > Decimal("0.00")],
        source_phase="Phase 9",
        scoring_rationale=f"Evaluated {len(cmp_factors)} compliance risk factor(s). Sum raw value: {raw_sum}, capped: {capped_score}.",
    )
    score = DimensionScore(
        dimension_id="DIM-CMP",
        dimension_name="Compliance Violation Risk",
        score=capped_score,
        status=DimensionStatus.AVAILABLE,
        weight=dim_weight,
        reweighted_weight=dim_weight,
        weighted_contribution=Decimal("0.00"),
        evidence=evidence,
    )
    return score, None


def score_extraction_quality_dimension(
    extraction_result: Optional[DocumentExtractionResult],
    profile: RiskProfile,
) -> Tuple[DimensionScore, Optional[SkippedRiskCheck]]:
    """Score DIM-EXT (Extraction Quality Uncertainty) using Decimal arithmetic."""
    dim_weight = profile.dimension_weights.get("DIM-EXT", Decimal("0.15"))

    if not extraction_result or not extraction_result.extraction:
        skipped = SkippedRiskCheck(
            dimension_id="DIM-EXT",
            reason="DocumentExtractionResult or extraction payload is missing.",
        )
        evidence = RiskEvidence(
            dimension_id="DIM-EXT",
            dimension_name="Extraction Quality Uncertainty",
            raw_score=Decimal("0.00"),
            weighted_contribution=Decimal("0.00"),
            weight=dim_weight,
            contributing_factors=[],
            source_phase="Phase 7",
            scoring_rationale="Extraction payload unavailable. Status set to INSUFFICIENT_DATA.",
        )
        score = DimensionScore(
            dimension_id="DIM-EXT",
            dimension_name="Extraction Quality Uncertainty",
            score=Decimal("0.00"),
            status=DimensionStatus.INSUFFICIENT_DATA,
            weight=dim_weight,
            reweighted_weight=dim_weight,
            weighted_contribution=Decimal("0.00"),
            evidence=evidence,
        )
        return score, skipped

    conf_float = extraction_result.extraction.extraction_confidence
    conf_dec = Decimal(str(conf_float))
    # Uncertainty score = (1.00 - confidence) * 100.00
    raw_uncertainty = (Decimal("1.00") - conf_dec) * Decimal("100.00")
    capped_score = min(max(Decimal("0.00"), raw_uncertainty), Decimal("100.00"))

    evidence = RiskEvidence(
        dimension_id="DIM-EXT",
        dimension_name="Extraction Quality Uncertainty",
        raw_score=capped_score,
        weighted_contribution=Decimal("0.00"),
        weight=dim_weight,
        contributing_factors=[f"confidence:{conf_float:.2f}"],
        source_phase="Phase 7",
        scoring_rationale=(
            f"Extraction confidence: {conf_float:.2f}. "
            f"Uncertainty formula (1.00 - {conf_dec}) * 100.00 = {capped_score}."
        ),
    )
    score = DimensionScore(
        dimension_id="DIM-EXT",
        dimension_name="Extraction Quality Uncertainty",
        score=capped_score,
        status=DimensionStatus.AVAILABLE,
        weight=dim_weight,
        reweighted_weight=dim_weight,
        weighted_contribution=Decimal("0.00"),
        evidence=evidence,
    )
    return score, None


def score_provenance_dimension(
    metadata: Optional[DocumentMetadata],
    profile: RiskProfile,
) -> Tuple[DimensionScore, Optional[SkippedRiskCheck]]:
    """Score DIM-PRV (Provenance Integrity Risk) using Decimal arithmetic."""
    dim_weight = profile.dimension_weights.get("DIM-PRV", Decimal("0.10"))

    if not metadata:
        skipped = SkippedRiskCheck(
            dimension_id="DIM-PRV",
            reason="DocumentMetadata is missing.",
        )
        evidence = RiskEvidence(
            dimension_id="DIM-PRV",
            dimension_name="Provenance Integrity Risk",
            raw_score=Decimal("0.00"),
            weighted_contribution=Decimal("0.00"),
            weight=dim_weight,
            contributing_factors=[],
            source_phase="Phase 5",
            scoring_rationale="DocumentMetadata unavailable. Status set to INSUFFICIENT_DATA.",
        )
        score = DimensionScore(
            dimension_id="DIM-PRV",
            dimension_name="Provenance Integrity Risk",
            score=Decimal("0.00"),
            status=DimensionStatus.INSUFFICIENT_DATA,
            weight=dim_weight,
            reweighted_weight=dim_weight,
            weighted_contribution=Decimal("0.00"),
            evidence=evidence,
        )
        return score, skipped

    raw_score = Decimal("0.00")
    factors = []

    if not metadata.checksum or not metadata.checksum.strip():
        raw_score += Decimal("60.00")
        factors.append("missing_checksum")

    if metadata.size_bytes == 0:
        raw_score += Decimal("40.00")
        factors.append("zero_byte_size")

    capped_score = min(raw_score, Decimal("100.00"))

    evidence = RiskEvidence(
        dimension_id="DIM-PRV",
        dimension_name="Provenance Integrity Risk",
        raw_score=capped_score,
        weighted_contribution=Decimal("0.00"),
        weight=dim_weight,
        contributing_factors=factors,
        source_phase="Phase 5",
        scoring_rationale=f"Evaluated metadata. Checksum present: {bool(metadata.checksum)}. Size: {metadata.size_bytes} bytes.",
    )
    score = DimensionScore(
        dimension_id="DIM-PRV",
        dimension_name="Provenance Integrity Risk",
        score=capped_score,
        status=DimensionStatus.AVAILABLE,
        weight=dim_weight,
        reweighted_weight=dim_weight,
        weighted_contribution=Decimal("0.00"),
        evidence=evidence,
    )
    return score, None


def score_data_completeness_dimension(
    forensic_result: Optional[ForensicAnalysisResult],
    compliance_result: Optional[ComplianceAnalysisResult],
    profile: RiskProfile,
) -> Tuple[DimensionScore, Optional[SkippedRiskCheck]]:
    """Score DIM-DAT (Data Completeness Uncertainty) using Decimal arithmetic."""
    dim_weight = profile.dimension_weights.get("DIM-DAT", Decimal("0.15"))

    total_checks = 0
    skipped_checks = 0

    if forensic_result:
        total_checks += len(forensic_result.deterministic_checks_run) + len(forensic_result.checks_skipped)
        skipped_checks += len(forensic_result.checks_skipped)

    if compliance_result:
        total_checks += len(compliance_result.checks_run) + len(compliance_result.checks_skipped)
        skipped_checks += len(compliance_result.checks_skipped)

    if total_checks == 0:
        skipped = SkippedRiskCheck(
            dimension_id="DIM-DAT",
            reason="No forensic or compliance checks were recorded for completeness evaluation.",
        )
        evidence = RiskEvidence(
            dimension_id="DIM-DAT",
            dimension_name="Data Completeness Uncertainty",
            raw_score=Decimal("0.00"),
            weighted_contribution=Decimal("0.00"),
            weight=dim_weight,
            contributing_factors=[],
            source_phase="Phase 8 + 9",
            scoring_rationale="Zero total checks recorded. Status set to INSUFFICIENT_DATA.",
        )
        score = DimensionScore(
            dimension_id="DIM-DAT",
            dimension_name="Data Completeness Uncertainty",
            score=Decimal("0.00"),
            status=DimensionStatus.INSUFFICIENT_DATA,
            weight=dim_weight,
            reweighted_weight=dim_weight,
            weighted_contribution=Decimal("0.00"),
            evidence=evidence,
        )
        return score, skipped

    ratio = Decimal(str(skipped_checks)) / Decimal(str(total_checks))
    raw_score = (ratio * Decimal("100.00")).quantize(Decimal("0.01"))
    capped_score = min(raw_score, Decimal("100.00"))

    evidence = RiskEvidence(
        dimension_id="DIM-DAT",
        dimension_name="Data Completeness Uncertainty",
        raw_score=capped_score,
        weighted_contribution=Decimal("0.00"),
        weight=dim_weight,
        contributing_factors=[f"skipped:{skipped_checks}/{total_checks}"],
        source_phase="Phase 8 + 9",
        scoring_rationale=f"Skipped checks ratio: {skipped_checks}/{total_checks} ({ratio * Decimal('100'):.2f}%).",
    )
    score = DimensionScore(
        dimension_id="DIM-DAT",
        dimension_name="Data Completeness Uncertainty",
        score=capped_score,
        status=DimensionStatus.AVAILABLE,
        weight=dim_weight,
        reweighted_weight=dim_weight,
        weighted_contribution=Decimal("0.00"),
        evidence=evidence,
    )
    return score, None
