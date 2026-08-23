from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from app.models.analysis import DocumentType
from app.models.risk import ProfileStatus, RiskContext, RiskProfile
from app.risk.profiles.financial_risk import DEFAULT_FINANCIAL_RISK_PROFILE

logger = logging.getLogger("papertrail.risk.registry")


class ProfileRegistrationError(Exception):
    """Raised when registering an invalid or duplicate profile version."""

    pass


class RiskProfileRegistry:
    """In-memory registry managing versioned RiskProfile instances."""

    def __init__(self, load_defaults: bool = True):
        # Key: (profile_id, version) -> RiskProfile
        self._profiles: Dict[Tuple[str, str], RiskProfile] = {}
        if load_defaults:
            self.register(DEFAULT_FINANCIAL_RISK_PROFILE)

    def register(self, profile: RiskProfile) -> None:
        """Register a new RiskProfile.

        Raises ProfileRegistrationError if duplicate or if dimension weights do not sum to Decimal('1.00').
        """
        key = (profile.profile_id, profile.version)
        if key in self._profiles:
            raise ProfileRegistrationError(
                f"RiskProfile '{profile.profile_id}' version '{profile.version}' is already registered."
            )

        total_weight = sum(profile.dimension_weights.values()) if profile.dimension_weights else Decimal("0.00")
        if total_weight != Decimal("1.00"):
            raise ProfileRegistrationError(
                f"RiskProfile '{profile.profile_id}' dimension weights must sum exactly to Decimal('1.00'), got {total_weight}"
            )

        self._profiles[key] = profile
        logger.info("Registered RiskProfile '%s' v%s", profile.profile_id, profile.version)

    def get_profile(self, profile_id: str, version: str) -> Optional[RiskProfile]:
        """Retrieve specific profile by profile_id and version string."""
        return self._profiles.get((profile_id, version))

    def list_profiles(self) -> List[RiskProfile]:
        """List all registered profiles."""
        return list(self._profiles.values())

    def get_applicable_profile(
        self,
        document_type: DocumentType,
        context: RiskContext,
    ) -> RiskProfile:
        """Return active RiskProfile matching context override or document_type scope."""
        if context.risk_profile_id:
            for (pid, ver), prof in self._profiles.items():
                if pid == context.risk_profile_id and prof.status == ProfileStatus.ACTIVE:
                    return prof

        doc_type_str = document_type.value.lower() if isinstance(document_type, DocumentType) else str(document_type).lower()

        for prof in self._profiles.values():
            if prof.status == ProfileStatus.ACTIVE:
                if not prof.scope or doc_type_str in [s.lower() for s in prof.scope]:
                    return prof

        return DEFAULT_FINANCIAL_RISK_PROFILE
