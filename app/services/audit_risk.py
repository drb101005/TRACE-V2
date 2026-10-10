"""Explainable audit-risk scoring and materiality assessment."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def _decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


@dataclass(frozen=True)
class MaterialityAssessment:
    amount: str | None
    threshold: str
    exceeds_threshold: bool | None
    percentage_of_materiality: str | None
    conclusion: str


def assess_materiality(
    amount: Any,
    materiality_threshold: Any,
) -> MaterialityAssessment:
    value = _decimal(amount)
    threshold = _decimal(materiality_threshold)

    if threshold is None or threshold <= 0:
        raise ValueError("Materiality threshold must be a positive finite amount")

    if value is None:
        return MaterialityAssessment(
            None, str(threshold), None, None, "REVIEW_AMOUNT_UNKNOWN"
        )

    ratio = abs(value) / threshold * Decimal("100")
    exceeds = abs(value) >= threshold

    return MaterialityAssessment(
        amount=str(value),
        threshold=str(threshold),
        exceeds_threshold=exceeds,
        percentage_of_materiality=str(ratio.quantize(Decimal("0.01"))),
        conclusion=(
            "AT_OR_ABOVE_MATERIALITY"
            if exceeds else "BELOW_MATERIALITY"
        ),
    )


def score_audit_risk(
    *,
    amount: Any,
    materiality_threshold: Any,
    rule_severity: str,
    evidence_status: str,
    related_party: bool = False,
    manual_override: int | None = None,
) -> dict:
    """
    Score an exception from 0-100 using explicit, inspectable components.

    The score prioritizes review; it does not determine fraud or misstatement.
    """
    severity_points = {
        "LOW": 10,
        "MEDIUM": 25,
        "HIGH": 40,
        "CRITICAL": 50,
    }
    evidence_points = {
        "VERIFIED": 0,
        "PENDING": 15,
        "MISSING": 25,
        "REJECTED": 30,
        "UNKNOWN": 20,
    }

    severity = str(rule_severity).upper()
    evidence = str(evidence_status).upper()

    if severity not in severity_points:
        raise ValueError(f"Unsupported severity: {rule_severity}")
    if evidence not in evidence_points:
        raise ValueError(f"Unsupported evidence status: {evidence_status}")

    materiality = assess_materiality(amount, materiality_threshold)
    amount_points = 0
    if materiality.exceeds_threshold is True:
        amount_points = 30
    elif materiality.exceeds_threshold is False:
        amount_points = min(
            20,
            int(Decimal(materiality.percentage_of_materiality or "0") / 5),
        )
    else:
        amount_points = 10

    related_party_points = 10 if related_party else 0
    raw_score = (
        severity_points[severity]
        + evidence_points[evidence]
        + amount_points
        + related_party_points
    )
    calculated_score = min(100, raw_score)

    if manual_override is not None:
        if isinstance(manual_override, bool) or not 0 <= manual_override <= 100:
            raise ValueError("Manual override must be an integer from 0 to 100")
        final_score = manual_override
    else:
        final_score = calculated_score

    return {
        "score": final_score,
        "calculated_score": calculated_score,
        "override_applied": manual_override is not None,
        "risk_level": (
            "CRITICAL" if final_score >= 80 else
            "HIGH" if final_score >= 60 else
            "MEDIUM" if final_score >= 30 else
            "LOW"
        ),
        "components": {
            "severity": severity_points[severity],
            "evidence": evidence_points[evidence],
            "amount": amount_points,
            "related_party": related_party_points,
        },
        "materiality": {
            "amount": materiality.amount,
            "threshold": materiality.threshold,
            "exceeds_threshold": materiality.exceeds_threshold,
            "percentage_of_materiality": materiality.percentage_of_materiality,
            "conclusion": materiality.conclusion,
        },
        "limitation": "Risk prioritization only; not a fraud or misstatement conclusion.",
    }


def rank_audit_exceptions(
    exceptions: Sequence[Mapping[str, Any]],
) -> list[dict]:
    """Sort scored exceptions by risk descending, with stable ID tie-breaking."""
    return sorted(
        (dict(item) for item in exceptions),
        key=lambda item: (
            -int(item["risk"]["score"]),
            str(item.get("finding_id") or item.get("rule_code") or ""),
        ),
    )
