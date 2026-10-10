import pytest

from app.services.audit_risk import (
    assess_materiality,
    rank_audit_exceptions,
    score_audit_risk,
)


def test_amount_above_materiality():
    result = assess_materiality("10000", "5000")
    assert result.exceeds_threshold is True
    assert result.conclusion == "AT_OR_ABOVE_MATERIALITY"
    assert result.percentage_of_materiality == "200.00"


def test_amount_below_materiality():
    result = assess_materiality("125", "5000")
    assert result.exceeds_threshold is False
    assert result.percentage_of_materiality == "2.50"


def test_unknown_amount_is_not_zero():
    result = assess_materiality(None, "5000")
    assert result.exceeds_threshold is None
    assert result.amount is None
    assert result.conclusion == "REVIEW_AMOUNT_UNKNOWN"


@pytest.mark.parametrize("threshold", ["0", "-1", None, "NaN"])
def test_invalid_materiality_threshold_rejected(threshold):
    with pytest.raises(ValueError):
        assess_materiality("100", threshold)


def test_risk_score_is_reproducible_and_explainable():
    kwargs = dict(
        amount="12000",
        materiality_threshold="5000",
        rule_severity="HIGH",
        evidence_status="MISSING",
        related_party=True,
    )
    first = score_audit_risk(**kwargs)
    second = score_audit_risk(**kwargs)

    assert first == second
    assert first["score"] == 100
    assert first["components"]["related_party"] == 10
    assert "not a fraud" in first["limitation"]


def test_manual_override_is_explicit():
    result = score_audit_risk(
        amount="100",
        materiality_threshold="5000",
        rule_severity="LOW",
        evidence_status="VERIFIED",
        manual_override=75,
    )
    assert result["score"] == 75
    assert result["override_applied"] is True
    assert result["calculated_score"] != result["score"]


@pytest.mark.parametrize("override", [-1, 101, True])
def test_invalid_manual_override_rejected(override):
    with pytest.raises(ValueError):
        score_audit_risk(
            amount="100",
            materiality_threshold="5000",
            rule_severity="LOW",
            evidence_status="VERIFIED",
            manual_override=override,
        )


def test_risk_ranking_is_descending_and_stable():
    records = [
        {"finding_id": "b", "risk": {"score": 80}},
        {"finding_id": "c", "risk": {"score": 30}},
        {"finding_id": "a", "risk": {"score": 80}},
    ]
    ranked = rank_audit_exceptions(records)
    assert [r["finding_id"] for r in ranked] == ["a", "b", "c"]
