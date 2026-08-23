from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class RiskLevel(str, Enum):
    """Categorical risk level classification based on composite score."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProfileStatus(str, Enum):
    """Lifecycle status of a risk profile."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class DimensionStatus(str, Enum):
    """Evaluation status of a risk dimension."""

    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SKIPPED = "SKIPPED"


class DecimalRiskLevelThresholds(BaseModel):
    """Threshold boundaries for risk level classification using Decimal representation."""

    critical: Decimal = Field(default=Decimal("75.00"))
    high: Decimal = Field(default=Decimal("50.00"))
    medium: Decimal = Field(default=Decimal("25.00"))


class RiskContext(BaseModel):
    """Explicit risk evaluation context supplied by caller.

    IMPORTANT: reference_datetime MUST be explicitly provided by caller.
    The RiskAssessmentEngine never reads the system clock directly.
    """

    reference_datetime: datetime
    organization_scope: Optional[str] = None
    risk_profile_id: Optional[str] = None
    jurisdiction_label: Optional[str] = None
    historical_risk_indicators: Dict[str, Decimal] = Field(default_factory=dict)
    risk_tolerance_overrides: Dict[str, Decimal] = Field(default_factory=dict)


class RiskFactor(BaseModel):
    """Individual risk signal parsed from upstream phase outputs."""

    factor_id: str
    category: str
    source_phase: str
    source_reference: str
    lineage_key: str
    severity_label: str
    raw_value: Decimal
    normalized_value: Decimal
    evidence_notes: str


class RiskEvidence(BaseModel):
    """Verifiable evidence supporting a risk dimension score."""

    dimension_id: str
    dimension_name: str
    raw_score: Decimal
    weighted_contribution: Decimal
    weight: Decimal
    contributing_factors: List[str] = Field(default_factory=list)
    source_phase: str
    scoring_rationale: str


class DimensionScore(BaseModel):
    """Score envelope for a single risk dimension."""

    dimension_id: str
    dimension_name: str
    score: Decimal
    status: DimensionStatus = DimensionStatus.AVAILABLE
    weight: Decimal
    reweighted_weight: Decimal
    weighted_contribution: Decimal
    max_possible: Decimal = Decimal("100.00")
    evidence: RiskEvidence


class SkippedRiskCheck(BaseModel):
    """Record of a risk check or dimension that was skipped during evaluation."""

    dimension_id: str
    reason: str


class TraceStep(BaseModel):
    """Single step in the calculation audit trace."""

    step_number: int
    step_name: str
    input_values: Dict[str, str] = Field(default_factory=dict)
    formula: str
    output_value: str


class CalculationTrace(BaseModel):
    """Complete, reproducible audit trace of the risk score calculation."""

    profile_id: str
    profile_version: str
    factors_evaluated: int = 0
    factors_deduplicated: int = 0
    reweighted_dimensions: Dict[str, str] = Field(default_factory=dict)
    dimension_raw_scores: Dict[str, str] = Field(default_factory=dict)
    dimension_weighted_contributions: Dict[str, str] = Field(default_factory=dict)
    unrounded_composite_score: str = "0.00"
    final_composite_score: str = "0.00"
    classification_level: str = "LOW"
    steps: List[TraceStep] = Field(default_factory=list)


class RiskAssessmentResult(BaseModel):
    """Complete risk assessment output envelope produced by RiskAssessmentEngine."""

    document_id: str
    composite_score: Decimal
    risk_level: RiskLevel
    dimension_scores: List[DimensionScore] = Field(default_factory=list)
    profile_id: str
    profile_version: str
    uncertainty_flag: bool = False
    review_recommended: bool = False
    checks_skipped: List[SkippedRiskCheck] = Field(default_factory=list)
    calculation_trace: Optional[CalculationTrace] = None
    assessment_summary: Optional[str] = None
    deterministic: bool = True


class RiskProfile(BaseModel):
    """Self-contained, versioned risk profile definition."""

    profile_id: str
    name: str
    version: str
    description: str
    scope: List[str] = Field(default_factory=list)
    dimension_weights: Dict[str, Decimal] = Field(default_factory=dict)
    risk_level_thresholds: DecimalRiskLevelThresholds = Field(default_factory=DecimalRiskLevelThresholds)
    correlation_policy: str = "LINEAGE_SOURCE_PRIORITY"
    missing_data_policy: str = "DYNAMIC_REWEIGHTING_WITH_UNCERTAINTY"
    status: ProfileStatus = ProfileStatus.ACTIVE

    @model_validator(mode="after")
    def validate_dimension_weights(self) -> "RiskProfile":
        if self.dimension_weights:
            total = sum(self.dimension_weights.values())
            if total != Decimal("1.00"):
                raise ValueError(
                    f"RiskProfile '{self.profile_id}' dimension weights must sum exactly to Decimal('1.00'), got {total}"
                )
        return self
