import logging
from decimal import Decimal
from typing import Dict, List

from app.models.risk import RiskFactor

logger = logging.getLogger("papertrail.risk.aggregation")


class RiskAggregationPolicy:
    """Policy enforcing evidence lineage deduplication to prevent double-counting across Phase 8 and Phase 9."""

    def aggregate_factors(self, factors: List[RiskFactor]) -> List[RiskFactor]:
        """Deduplicate risk factors sharing the same lineage_key without mutating input objects.

        When a Forensic finding (Phase 8) and a Compliance failure (Phase 9) share the same underlying
        evidence lineage, Compliance (Phase 9) is selected as the primary factor, and the non-primary
        factor is returned as a new copy with normalized_value = Decimal("0.00") to prevent artificial double counting.
        Original input RiskFactor instances remain 100% unmutated.
        """
        grouped: Dict[str, List[RiskFactor]] = {}
        for factor in factors:
            grouped.setdefault(factor.lineage_key, []).append(factor)

        aggregated: List[RiskFactor] = []
        for lineage_key, factor_group in grouped.items():
            if len(factor_group) == 1:
                aggregated.append(factor_group[0])
            else:
                # Correlated group: select Compliance finding (Phase 9) as primary
                primary = next((f for f in factor_group if f.source_phase == "Phase 9"), factor_group[0])
                logger.info(
                    "Correlated lineage key '%s' found %d factors. Primary selected: '%s' (%s)",
                    lineage_key,
                    len(factor_group),
                    primary.factor_id,
                    primary.source_phase,
                )
                for f in factor_group:
                    if f != primary:
                        f_copy = f.model_copy(
                            update={
                                "normalized_value": Decimal("0.00"),
                                "evidence_notes": f.evidence_notes + f" [Corroborated by primary factor '{primary.factor_id}']",
                            }
                        )
                        aggregated.append(f_copy)
                    else:
                        aggregated.append(primary)

        return aggregated
