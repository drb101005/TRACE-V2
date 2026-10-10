"""Risk assessment adapter for persisted TRACE-V2 audit findings."""

import json
from typing import Any

from app.services.audit_risk import score_audit_risk


def assess_finding_risk(
    finding: Any,
    materiality_threshold: str,
    evidence_status: str = "UNKNOWN",
    related_party: bool = False,
) -> dict:
    """Score an ORM finding or compatible record without mutating it."""
    calculation = getattr(finding, "calculation_json", None)
    calculation_data = {}

    if calculation:
        try:
            parsed = json.loads(calculation) if isinstance(calculation, str) else calculation
            if isinstance(parsed, dict):
                calculation_data = parsed
        except (ValueError, TypeError):
            calculation_data = {}

    amount = getattr(finding, "amount_under_review", None)
    if amount is None:
        amount = calculation_data.get("amount_under_review")

    severity = str(getattr(finding, "severity", "MEDIUM") or "MEDIUM").upper()
    if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        severity = "MEDIUM"

    result = score_audit_risk(
        amount=amount,
        materiality_threshold=materiality_threshold,
        rule_severity=severity,
        evidence_status=evidence_status,
        related_party=related_party,
    )

    result["finding_id"] = str(getattr(finding, "id", ""))
    result["rule_code"] = str(getattr(finding, "rule_code", ""))
    result["finding_status"] = str(getattr(finding, "status", "UNKNOWN"))
    return result


def rank_finding_risks(
    findings: list[Any],
    materiality_threshold: str,
    evidence_status_by_finding: dict[str, str] | None = None,
    related_party_finding_ids: set[str] | None = None,
) -> list[dict]:
    """Return a deterministic risk-ranked assessment without changing findings."""
    evidence_status_by_finding = evidence_status_by_finding or {}
    related_party_finding_ids = related_party_finding_ids or set()

    assessments = []
    for finding in findings:
        finding_id = str(getattr(finding, "id", ""))
        assessments.append(
            assess_finding_risk(
                finding,
                materiality_threshold,
                evidence_status=evidence_status_by_finding.get(
                    finding_id, "UNKNOWN"
                ),
                related_party=finding_id in related_party_finding_ids,
            )
        )

    return sorted(
        assessments,
        key=lambda item: (-item["score"], item["finding_id"]),
    )
