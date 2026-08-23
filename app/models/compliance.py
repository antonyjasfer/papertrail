from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    """Result status of a compliance control or rule evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PolicyStatus(str, Enum):
    """Lifecycle status of a compliance policy."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class ControlSeverity(str, Enum):
    """Severity classification for a compliance control."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ControlApplicability(BaseModel):
    """Conditions governing whether a compliance control applies to a document."""

    document_types: List[str] = Field(default_factory=list)
    required_extraction_fields: List[str] = Field(default_factory=list)
    required_forensic_findings: List[str] = Field(default_factory=list)


class ComplianceControl(BaseModel):
    """Single compliance control unit within a policy."""

    control_id: str
    policy_id: str
    name: str
    description: str
    applicability: ControlApplicability = Field(default_factory=ControlApplicability)
    rules: List[str] = Field(default_factory=list)
    severity: ControlSeverity = ControlSeverity.HIGH
    required_evidence: List[str] = Field(default_factory=list)


class CompliancePolicy(BaseModel):
    """Versioned compliance policy grouping controls and applicability metadata."""

    policy_id: str
    name: str
    version: str  # Semantic version string e.g. "1.0.0"
    description: str
    scope: List[str] = Field(default_factory=list)  # Document types in scope
    effective_from: str  # ISO-8601 date string
    effective_until: Optional[str] = None  # ISO-8601 date string or None
    status: PolicyStatus = PolicyStatus.ACTIVE
    controls: List[ComplianceControl] = Field(default_factory=list)
    jurisdiction_labels: List[str] = Field(default_factory=list)


class ComplianceContext(BaseModel):
    """Explicit evaluation context supplied by caller.

    IMPORTANT: reference_datetime MUST be explicitly provided by the caller.
    The engine never accesses the system clock directly.
    """

    reference_datetime: datetime
    organization_scope: Optional[str] = None
    policy_scope: Optional[str] = None
    jurisdiction_label: Optional[str] = None
    configured_thresholds: Dict[str, str] = Field(default_factory=dict)


class ComplianceEvidence(BaseModel):
    """Verifiable evidence supporting a compliance finding."""

    policy_reference: str
    control_reference: str
    rule_reference: str
    observed_value: Optional[str] = None
    expected_condition: Optional[str] = None
    evaluation_result: str
    source_phase: str
    forensic_finding_codes: List[str] = Field(default_factory=list)
    context_notes: Optional[str] = None


class ComplianceFinding(BaseModel):
    """Result finding produced by a compliance evaluation."""

    finding_id: str
    policy_id: str
    policy_version: str
    control_id: str
    rule_id: str
    status: ComplianceStatus
    evidence: ComplianceEvidence
    description: str
    deterministic: bool = True


class SkippedComplianceCheck(BaseModel):
    """Record of a compliance check skipped during evaluation."""

    policy_id: str
    control_id: str
    rule_id: Optional[str] = None
    reason: str


class PolicyEvaluationSummary(BaseModel):
    """Summary metrics of evaluation for a single policy."""

    policy_id: str
    policy_version: str
    controls_evaluated: int = 0
    controls_passed: int = 0
    controls_failed: int = 0
    controls_review: int = 0
    controls_not_applicable: int = 0
    controls_insufficient_evidence: int = 0


class ComplianceRuleResult(BaseModel):
    """Result envelope returned by individual rule evaluation."""

    rule_id: str
    status: ComplianceStatus
    evidence: ComplianceEvidence
    description: str


class ComplianceAnalysisResult(BaseModel):
    """Complete envelope containing compliance findings and policy summaries."""

    document_id: str
    findings: List[ComplianceFinding] = Field(default_factory=list)
    finding_count: int = 0
    policy_summaries: List[PolicyEvaluationSummary] = Field(default_factory=list)
    checks_run: List[str] = Field(default_factory=list)
    checks_skipped: List[SkippedComplianceCheck] = Field(default_factory=list)
    policies_evaluated: List[str] = Field(default_factory=list)
    evidence_summary: Optional[str] = None
