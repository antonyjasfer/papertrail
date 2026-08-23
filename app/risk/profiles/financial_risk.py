from decimal import Decimal

from app.models.risk import DecimalRiskLevelThresholds, ProfileStatus, RiskProfile

DEFAULT_FINANCIAL_RISK_PROFILE = RiskProfile(
    profile_id="RP-FIN-001",
    name="Financial Document Risk Profile",
    version="1.0.0",
    description=(
        "Standard organizational risk profile governing multi-dimensional risk evaluation for commercial "
        "financial documents (invoices, receipts, purchase orders, expense reports)."
    ),
    scope=["invoice", "receipt", "purchase_order", "expense_report"],
    dimension_weights={
        "DIM-FOR": Decimal("0.30"),
        "DIM-CMP": Decimal("0.30"),
        "DIM-EXT": Decimal("0.15"),
        "DIM-PRV": Decimal("0.10"),
        "DIM-DAT": Decimal("0.15"),
    },
    risk_level_thresholds=DecimalRiskLevelThresholds(
        critical=Decimal("75.00"),
        high=Decimal("50.00"),
        medium=Decimal("25.00"),
    ),
    correlation_policy="LINEAGE_SOURCE_PRIORITY",
    missing_data_policy="DYNAMIC_REWEIGHTING_WITH_UNCERTAINTY",
    status=ProfileStatus.ACTIVE,
)
