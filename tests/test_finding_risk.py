from types import SimpleNamespace

from app.services.finding_risk import assess_finding_risk, rank_finding_risks


def make_finding(identifier, amount, severity="MEDIUM", status="DRAFT"):
    return SimpleNamespace(
        id=identifier,
        rule_code="TEST_RULE",
        severity=severity,
        status=status,
        amount_under_review=amount,
        calculation_json="{}",
    )


def test_finding_assessment_includes_identity_and_status():
    finding = make_finding("f-1", "12000", "HIGH", "DRAFT")

    result = assess_finding_risk(finding, "5000", evidence_status="MISSING")

    assert result["finding_id"] == "f-1"
    assert result["rule_code"] == "TEST_RULE"
    assert result["finding_status"] == "DRAFT"
    assert result["materiality"]["exceeds_threshold"] is True


def test_ranking_is_deterministic_and_does_not_mutate_findings():
    findings = [
        make_finding("f-2", "100", "LOW"),
        make_finding("f-1", "10000", "HIGH"),
    ]
    original_statuses = [finding.status for finding in findings]

    first = rank_finding_risks(findings, "1000")
    second = rank_finding_risks(findings, "1000")

    assert first == second
    assert first[0]["finding_id"] == "f-1"
    assert [finding.status for finding in findings] == original_statuses


def test_unknown_amount_remains_unknown():
    finding = make_finding("f-3", None)

    result = assess_finding_risk(finding, "5000")

    assert result["materiality"]["exceeds_threshold"] is None
    assert result["materiality"]["conclusion"] == "REVIEW_AMOUNT_UNKNOWN"


def test_invalid_stored_severity_uses_conservative_default():
    finding = make_finding("f-4", "100", "UNEXPECTED")

    result = assess_finding_risk(finding, "5000")

    assert result["components"]["severity"] == 25
