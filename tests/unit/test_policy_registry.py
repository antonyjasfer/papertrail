from datetime import datetime, timezone
import pytest

from app.compliance.policies.financial_integrity import INVOICE_FINANCIAL_INTEGRITY_POLICY
from app.compliance.registry import PolicyRegistrationError, PolicyRegistry
from app.models.analysis import DocumentType
from app.models.compliance import (
    ComplianceContext,
    CompliancePolicy,
    PolicyStatus,
)


def test_default_policy_registration():
    registry = PolicyRegistry(load_defaults=True)
    policies = registry.list_policies()
    assert len(policies) >= 1
    p = registry.get_policy("POL-FIN-001", "1.0.0")
    assert p is not None
    assert p.name == INVOICE_FINANCIAL_INTEGRITY_POLICY.name


def test_duplicate_version_registration_rejected():
    registry = PolicyRegistry(load_defaults=True)
    duplicate_policy = CompliancePolicy(
        policy_id="POL-FIN-001",
        name="Duplicate Policy",
        version="1.0.0",
        description="Test duplicate registration",
        effective_from="2026-01-01T00:00:00Z",
    )
    with pytest.raises(PolicyRegistrationError) as exc_info:
        registry.register(duplicate_policy)

    assert "already registered" in str(exc_info.value)


def test_active_policy_retrieval_and_date_filtering():
    registry = PolicyRegistry(load_defaults=False)

    policy = CompliancePolicy(
        policy_id="POL-TEST-001",
        name="Test Date Window Policy",
        version="1.0.0",
        description="Testing effective date filtering",
        effective_from="2026-01-01T00:00:00Z",
        effective_until="2026-12-31T23:59:59Z",
        status=PolicyStatus.ACTIVE,
        scope=["invoice"],
    )
    registry.register(policy)

    # Date within window (August 2026) -> Active
    ctx_active = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    active_policies = registry.get_applicable_policies(DocumentType.INVOICE, ctx_active)
    assert len(active_policies) == 1

    # Date outside window (2027) -> Inactive
    ctx_future = ComplianceContext(reference_datetime=datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
    inactive_policies = registry.get_applicable_policies(DocumentType.INVOICE, ctx_future)
    assert len(inactive_policies) == 0


def test_deprecated_policy_exclusion():
    registry = PolicyRegistry(load_defaults=False)
    deprecated_policy = CompliancePolicy(
        policy_id="POL-OLD-001",
        name="Deprecated Policy",
        version="1.0.0",
        description="Deprecated test policy",
        effective_from="2025-01-01T00:00:00Z",
        status=PolicyStatus.DEPRECATED,
        scope=["invoice"],
    )
    registry.register(deprecated_policy)

    ctx = ComplianceContext(reference_datetime=datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc))
    policies = registry.get_applicable_policies(DocumentType.INVOICE, ctx)
    assert len(policies) == 0
