from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, List, Optional, Tuple

from app.models.analysis import DocumentExtractionResult, DocumentType
from app.models.compliance import ComplianceAnalysisResult
from app.models.document import DocumentMetadata
from app.models.forensics import ForensicAnalysisResult
from app.models.risk import (
    CalculationTrace,
    DecimalRiskLevelThresholds,
    DimensionScore,
    DimensionStatus,
    RiskAssessmentResult,
    RiskContext,
    RiskLevel,
    RiskProfile,
    SkippedRiskCheck,
    TraceStep,
)
from app.risk.aggregation import RiskAggregationPolicy
from app.risk.registry import RiskProfileRegistry
from app.risk.scorers import (
    parse_all_risk_factors,
    score_compliance_dimension,
    score_data_completeness_dimension,
    score_extraction_quality_dimension,
    score_forensic_dimension,
    score_provenance_dimension,
)

logger = logging.getLogger("papertrail.risk.engine")


class RiskAssessmentEngine:
    """Deterministic Risk Assessment Engine for PaperTrail AI.

    Evaluates extraction results, document metadata, forensic findings, and compliance analysis results
    against versioned RiskProfiles using exact Decimal arithmetic.

    CRITICAL DETERMINISM RULES:
    1. Zero system clock reads (no datetime.now() or datetime.utcnow()).
    2. Context parameter must be explicitly provided by caller with reference_datetime.
    3. Zero LLM/Gemini dependencies.
    4. Zero database queries or writes.
    5. Zero WorkflowState mutations.
    6. Exact Decimal arithmetic for all score calculations.
    """

    def __init__(
        self,
        profile_registry: Optional[RiskProfileRegistry] = None,
        aggregation_policy: Optional[RiskAggregationPolicy] = None,
    ):
        self.profile_registry = profile_registry or RiskProfileRegistry()
        self.aggregation_policy = aggregation_policy or RiskAggregationPolicy()

    def assess(
        self,
        extraction_result: Optional[DocumentExtractionResult],
        metadata: Optional[DocumentMetadata],
        forensic_result: Optional[ForensicAnalysisResult],
        compliance_result: Optional[ComplianceAnalysisResult],
        context: RiskContext,
    ) -> RiskAssessmentResult:
        """Execute deterministic multi-dimensional risk assessment using Decimal arithmetic."""
        if context is None or not isinstance(context, RiskContext) or context.reference_datetime is None:
            raise ValueError("RiskContext with explicit reference_datetime is required for risk assessment.")

        doc_id = metadata.document_id if metadata else "N/A"
        doc_type = (
            extraction_result.extraction.document_type
            if extraction_result and extraction_result.extraction
            else DocumentType.UNKNOWN
        )

        logger.info(
            "Evaluating risk assessment for document '%s' (Type: %s, Ref Time: %s)",
            doc_id,
            doc_type.value,
            context.reference_datetime.isoformat(),
        )

        profile = self.profile_registry.get_applicable_profile(doc_type, context)
        trace_steps: List[TraceStep] = []
        step_counter = 0

        # Step 1: Parse Raw Risk Factors
        step_counter += 1
        raw_factors = parse_all_risk_factors(
            extraction_result=extraction_result,
            metadata=metadata,
            forensic_result=forensic_result,
            compliance_result=compliance_result,
        )
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Factor Parsing",
                input_values={"raw_factor_count": str(len(raw_factors))},
                formula="parse_all_risk_factors(prior_phase_outputs)",
                output_value=f"Parsed {len(raw_factors)} raw risk factors",
            )
        )

        # Step 2: Lineage Deduplication via RiskAggregationPolicy
        step_counter += 1
        aggregated_factors = self.aggregation_policy.aggregate_factors(raw_factors)
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Lineage Aggregation",
                input_values={
                    "raw_factors": str(len(raw_factors)),
                    "policy": profile.correlation_policy,
                },
                formula="RiskAggregationPolicy.aggregate_factors(raw_factors)",
                output_value=f"Deduplicated to {len(aggregated_factors)} factors",
            )
        )

        # Step 3: Evaluate Dimension Scores
        all_skipped: List[SkippedRiskCheck] = []

        dim_for, skip_for = score_forensic_dimension(aggregated_factors, forensic_result, profile)
        if skip_for:
            all_skipped.append(skip_for)

        dim_cmp, skip_cmp = score_compliance_dimension(aggregated_factors, compliance_result, profile)
        if skip_cmp:
            all_skipped.append(skip_cmp)

        dim_ext, skip_ext = score_extraction_quality_dimension(extraction_result, profile)
        if skip_ext:
            all_skipped.append(skip_ext)

        dim_prv, skip_prv = score_provenance_dimension(metadata, profile)
        if skip_prv:
            all_skipped.append(skip_prv)

        dim_dat, skip_dat = score_data_completeness_dimension(forensic_result, compliance_result, profile)
        if skip_dat:
            all_skipped.append(skip_dat)

        dim_scores_dict: Dict[str, DimensionScore] = {
            "DIM-FOR": dim_for,
            "DIM-CMP": dim_cmp,
            "DIM-EXT": dim_ext,
            "DIM-PRV": dim_prv,
            "DIM-DAT": dim_dat,
        }

        step_counter += 1
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Dimension Scoring",
                input_values={d: str(score.score) for d, score in dim_scores_dict.items()},
                formula="score_dimension(factors, payload, profile)",
                output_value="Computed raw dimension scores",
            )
        )

        # Step 4: Dynamic Weight Reweighting for Missing Evidence
        active_dims = {d: s for d, s in dim_scores_dict.items() if s.status == DimensionStatus.AVAILABLE}
        sum_active_weights = sum(s.weight for s in active_dims.values()) if active_dims else Decimal("0.00")

        reweighted_map: Dict[str, Decimal] = {}
        if sum_active_weights > Decimal("0.00"):
            for d_id, score_obj in dim_scores_dict.items():
                if score_obj.status == DimensionStatus.AVAILABLE:
                    reweight = score_obj.weight / sum_active_weights
                    reweighted_map[d_id] = reweight
                    score_obj.reweighted_weight = reweight
                    score_obj.weighted_contribution = score_obj.score * reweight
                else:
                    reweighted_map[d_id] = Decimal("0.00")
                    score_obj.reweighted_weight = Decimal("0.00")
                    score_obj.weighted_contribution = Decimal("0.00")

        step_counter += 1
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Dynamic Reweighting",
                input_values={
                    "active_dimensions": str(list(active_dims.keys())),
                    "sum_active_weights": str(sum_active_weights),
                },
                formula="w_d' = w_d / sum(w_active)",
                output_value=f"Reweighted active weights: {reweighted_map}",
            )
        )

        # Step 5: Compute Composite Score
        unrounded_composite = sum(
            s.weighted_contribution for s in dim_scores_dict.values() if s.status == DimensionStatus.AVAILABLE
        )
        final_composite = unrounded_composite.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        step_counter += 1
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Composite Quantization",
                input_values={
                    "unrounded": str(unrounded_composite),
                    "rounding_mode": "ROUND_HALF_UP",
                },
                formula="sum(score_d * reweight_d).quantize(0.01)",
                output_value=str(final_composite),
            )
        )

        # Step 6: Validate & Resolve Risk Level Thresholds
        thresholds = self._resolve_thresholds(profile, context)
        risk_level = self._classify_risk_level(final_composite, thresholds)

        step_counter += 1
        trace_steps.append(
            TraceStep(
                step_number=step_counter,
                step_name="Risk Classification",
                input_values={
                    "composite": str(final_composite),
                    "threshold_critical": str(thresholds.critical),
                    "threshold_high": str(thresholds.high),
                    "threshold_medium": str(thresholds.medium),
                },
                formula="classify_risk_level(composite, thresholds)",
                output_value=risk_level.value,
            )
        )

        # Step 7: Uncertainty & Review Flags
        uncertainty_flag = len(all_skipped) > 0 or any(
            s.status == DimensionStatus.INSUFFICIENT_DATA for s in dim_scores_dict.values()
        )
        low_confidence = (
            extraction_result is not None
            and extraction_result.extraction is not None
            and extraction_result.extraction.extraction_confidence < 0.70
        )
        review_recommended = (risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)) or uncertainty_flag or low_confidence

        # Step 8: Build Audit CalculationTrace
        trace = CalculationTrace(
            profile_id=profile.profile_id,
            profile_version=profile.version,
            factors_evaluated=len(raw_factors),
            factors_deduplicated=len(aggregated_factors),
            reweighted_dimensions={k: str(v) for k, v in reweighted_map.items()},
            dimension_raw_scores={k: str(v.score) for k, v in dim_scores_dict.items()},
            dimension_weighted_contributions={k: str(v.weighted_contribution) for k, v in dim_scores_dict.items()},
            unrounded_composite_score=str(unrounded_composite),
            final_composite_score=str(final_composite),
            classification_level=risk_level.value,
            steps=trace_steps,
        )

        summary_text = (
            f"Risk assessment completed for document '{doc_id}' using profile '{profile.profile_id} v{profile.version}'. "
            f"Composite Risk Score: {final_composite} ({risk_level.value}). "
            f"Evaluated {len(raw_factors)} risk factor(s) ({len(aggregated_factors)} post-deduplication). "
            f"Uncertainty Flag: {uncertainty_flag}, Review Recommended: {review_recommended}."
        )

        logger.info(summary_text)

        return RiskAssessmentResult(
            document_id=doc_id,
            composite_score=final_composite,
            risk_level=risk_level,
            dimension_scores=list(dim_scores_dict.values()),
            profile_id=profile.profile_id,
            profile_version=profile.version,
            uncertainty_flag=uncertainty_flag,
            review_recommended=review_recommended,
            checks_skipped=all_skipped,
            calculation_trace=trace,
            assessment_summary=summary_text,
            deterministic=True,
        )

    def _resolve_thresholds(
        self,
        profile: RiskProfile,
        context: RiskContext,
    ) -> DecimalRiskLevelThresholds:
        """Resolve risk level thresholds, applying and validating caller overrides if present."""
        base = profile.risk_level_thresholds
        if not context.risk_tolerance_overrides:
            return base

        overrides = context.risk_tolerance_overrides

        crit = overrides.get("critical", base.critical)
        high = overrides.get("high", base.high)
        med = overrides.get("medium", base.medium)

        # Validate caller overrides: thresholds must maintain critical >= high >= medium
        if not (crit >= high >= med):
            logger.warning(
                "Caller risk_tolerance_overrides invalid (%s >= %s >= %s violated). Falling back to profile defaults.",
                crit,
                high,
                med,
            )
            return base

        return DecimalRiskLevelThresholds(critical=crit, high=high, medium=med)

    def _classify_risk_level(
        self,
        score: Decimal,
        thresholds: DecimalRiskLevelThresholds,
    ) -> RiskLevel:
        """Classify risk level from composite Decimal score."""
        if score >= thresholds.critical:
            return RiskLevel.CRITICAL
        elif score >= thresholds.high:
            return RiskLevel.HIGH
        elif score >= thresholds.medium:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
