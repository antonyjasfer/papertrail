import logging
from typing import Dict, List, Optional, Tuple

from app.compliance.policies.financial_integrity import INVOICE_FINANCIAL_INTEGRITY_POLICY
from app.compliance.rules import DEFAULT_COMPLIANCE_RULES, BaseComplianceRule
from app.models.analysis import DocumentType
from app.models.compliance import (
    ComplianceContext,
    ComplianceControl,
    CompliancePolicy,
    PolicyStatus,
)

logger = logging.getLogger("papertrail.compliance.registry")


class PolicyRegistrationError(Exception):
    """Raised when registering an invalid or duplicate policy version."""

    pass


class PolicyRegistry:
    """In-memory registry for versioned compliance policies."""

    def __init__(self, load_defaults: bool = True):
        # Key: (policy_id, version) -> CompliancePolicy
        self._policies: Dict[Tuple[str, str], CompliancePolicy] = {}
        if load_defaults:
            self.register(INVOICE_FINANCIAL_INTEGRITY_POLICY)

    def register(self, policy: CompliancePolicy) -> None:
        """Register a new policy.

        Raises PolicyRegistrationError if (policy_id, version) is already registered.
        """
        key = (policy.policy_id, policy.version)
        if key in self._policies:
            raise PolicyRegistrationError(
                f"Policy '{policy.policy_id}' version '{policy.version}' is already registered."
            )

        # Validate with Pydantic model (policy is already validated if passed as instance)
        self._policies[key] = policy
        logger.info("Registered CompliancePolicy '%s' v%s", policy.policy_id, policy.version)

    def get_policy(self, policy_id: str, version: str) -> Optional[CompliancePolicy]:
        """Retrieve specific policy by policy_id and version string."""
        return self._policies.get((policy_id, version))

    def list_policies(self) -> List[CompliancePolicy]:
        """List all registered policies."""
        return list(self._policies.values())

    def get_active_policies(self, context: ComplianceContext) -> List[CompliancePolicy]:
        """Return active policies where context reference_datetime falls within effective dates."""
        active: List[CompliancePolicy] = []
        ref_iso = context.reference_datetime.isoformat()

        for policy in self._policies.values():
            if policy.status != PolicyStatus.ACTIVE:
                continue

            # Effective date filtering
            if policy.effective_from and ref_iso < policy.effective_from:
                continue
            if policy.effective_until and ref_iso > policy.effective_until:
                continue

            # Scope / Jurisdiction label matching
            if context.jurisdiction_label and policy.jurisdiction_labels:
                if context.jurisdiction_label not in policy.jurisdiction_labels and "GLOBAL" not in policy.jurisdiction_labels:
                    continue

            active.append(policy)

        return active

    def get_applicable_policies(
        self,
        document_type: DocumentType,
        context: ComplianceContext,
    ) -> List[CompliancePolicy]:
        """Return active policies applicable to the given document_type and context."""
        active_policies = self.get_active_policies(context)
        doc_type_str = document_type.value.lower() if isinstance(document_type, DocumentType) else str(document_type).lower()

        applicable: List[CompliancePolicy] = []
        for policy in active_policies:
            if not policy.scope or doc_type_str in [s.lower() for s in policy.scope]:
                applicable.append(policy)

        return applicable


class ComplianceRuleRegistry:
    """Registry managing executable compliance rule instances keyed by rule_id."""

    def __init__(self, load_defaults: bool = True):
        self._rules: Dict[str, BaseComplianceRule] = {}
        if load_defaults:
            for rule in DEFAULT_COMPLIANCE_RULES:
                self.register(rule)

    def register(self, rule: BaseComplianceRule) -> None:
        """Register a compliance rule by its unique RULE_ID."""
        self._rules[rule.RULE_ID] = rule
        logger.debug("Registered BaseComplianceRule '%s'", rule.RULE_ID)

    def get_rule(self, rule_id: str) -> Optional[BaseComplianceRule]:
        """Retrieve rule by rule_id."""
        return self._rules.get(rule_id)

    def get_rules_for_control(self, control: ComplianceControl) -> List[BaseComplianceRule]:
        """Retrieve rule instances referenced by a ComplianceControl."""
        resolved: List[BaseComplianceRule] = []
        for rid in control.rules:
            rule_inst = self.get_rule(rid)
            if rule_inst:
                resolved.append(rule_inst)
        return resolved
