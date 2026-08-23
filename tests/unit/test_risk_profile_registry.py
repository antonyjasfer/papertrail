from decimal import Decimal
from datetime import datetime, timezone
import pytest

from app.models.analysis import DocumentType
from app.models.risk import DecimalRiskLevelThresholds, ProfileStatus, RiskContext, RiskProfile
from app.risk.profiles.financial_risk import DEFAULT_FINANCIAL_RISK_PROFILE
from app.risk.registry import ProfileRegistrationError, RiskProfileRegistry


def test_default_profile_registered():
    registry = RiskProfileRegistry(load_defaults=True)
    prof = registry.get_profile("RP-FIN-001", "1.0.0")
    assert prof is not None
    assert prof.name == "Financial Document Risk Profile"
    assert prof.status == ProfileStatus.ACTIVE
    assert sum(prof.dimension_weights.values()) == Decimal("1.00")


def test_duplicate_profile_registration_rejected():
    registry = RiskProfileRegistry(load_defaults=True)
    with pytest.raises(ProfileRegistrationError, match="already registered"):
        registry.register(DEFAULT_FINANCIAL_RISK_PROFILE)


def test_invalid_weight_sum_rejected():
    registry = RiskProfileRegistry(load_defaults=False)
    with pytest.raises((ProfileRegistrationError, ValueError)):
        invalid_prof = RiskProfile(
            profile_id="RP-TEST-001",
            name="Invalid Weight Profile",
            version="1.0.0",
            description="Test profile",
            dimension_weights={
                "DIM-FOR": Decimal("0.50"),
                "DIM-CMP": Decimal("0.60"),  # Sums to 1.10
            },
        )
        registry.register(invalid_prof)


def test_get_applicable_profile():
    registry = RiskProfileRegistry(load_defaults=True)
    ctx = RiskContext(reference_datetime=datetime.now(timezone.utc))

    prof = registry.get_applicable_profile(DocumentType.INVOICE, ctx)
    assert prof.profile_id == "RP-FIN-001"

    # Override by profile_id
    ctx_override = RiskContext(reference_datetime=datetime.now(timezone.utc), risk_profile_id="RP-FIN-001")
    prof_override = registry.get_applicable_profile(DocumentType.OTHER, ctx_override)
    assert prof_override.profile_id == "RP-FIN-001"
