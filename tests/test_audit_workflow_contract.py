from fastapi.testclient import TestClient

from app.main import app


def test_audit_workflow_api_contract():
    """Protect the key endpoints required for the audit workflow."""
    schema = app.openapi()
    paths = schema["paths"]

    required = {
        "/api/v1/auth/login": {"post"},
        "/api/v1/engagements/{engagement_id}/uploads": {"post"},
        "/api/v1/uploads/{upload_id}/ingest": {"post"},
        "/api/v1/uploads/{upload_id}/validation": {"get"},
        "/api/v1/engagements/{engagement_id}/audit-runs": {"post"},
        "/api/v1/ai-audit/reconcile": {"post"},
        "/api/v1/ai-audit/execute-cutoff-test": {"post"},
        "/api/v1/ai-audit/sample-sales-tod": {"post"},
        "/api/v1/ai-audit/findings": {"post", "get"},
        "/api/v1/ai-audit/audit-trail/verify": {"get"},
    }

    for path, methods in required.items():
        assert path in paths, f"Missing API path: {path}"
        actual = {method.lower() for method in paths[path]}
        assert methods <= actual, (
            f"{path}: missing methods {methods - actual}"
        )

    workpaper_paths = [
        path for path in paths
        if path.endswith("/workpaper")
    ]
    assert workpaper_paths, "Audit workpaper export endpoint is missing"


def test_protected_audit_endpoints_require_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/ai-audit/audit-trail/verify")
        assert response.status_code in {401, 422}
