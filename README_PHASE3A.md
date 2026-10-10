# TRACE-V2 Phase 3A overlay

## What this patch adds
- Versioned deterministic sales-register audit procedure.
- Persistent audit runs and draft findings with source record IDs/row numbers.
- Checks for duplicate invoice numbers, missing/invalid invoice number/amount/date,
  invoice arithmetic mismatch, and invoice dates outside the engagement period.
- Decimal-based money arithmetic, stable rule/engine versions and repeatable fingerprints.
- Role-gated execution (`ADMIN`, `INDEPENDENT_AUDITOR`, `HUMAN_AUDITOR`); client users cannot run tests.
- API endpoints:
  - `POST /api/v1/engagements/{engagement_id}/audit-runs?upload_id={upload_id}`
  - `GET /api/v1/engagements/{engagement_id}/audit-runs`
  - `GET /api/v1/audit-runs/{run_id}`
  - `GET /api/v1/audit-runs/{run_id}/findings`
- Tests for arithmetic, determinism and missing data.

## Apply
Extract the zip at the repository root, preserving directories, and allow overwrite for the included `app/main.py`, `app/models/__init__.py`, and `app/api/v1/router.py`.
This patch uses `Base.metadata.create_all`, which your existing app calls at startup; it adds tables without deleting existing tables. Back up `revenue_audit.db` first.

## Run
```bash
cd /home/drb/Documents/GitHub/TRACE-V2
source .venv/bin/activate
python -m pytest -q
```
Restart the existing uvicorn server after tests pass.

## Test API
Use `INDEPENDENT_AUDITOR` account for running audit tests:
```bash
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"auditor@example.com","password":"DemoPass123!"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
ENGAGEMENT_ID="0f4d0104-dd68-4500-828a-9ee6391484c9"
UPLOAD_ID="d172f42f-6c72-4442-bc94-aa74049f87c4"
curl -sS -X POST "http://127.0.0.1:8000/api/v1/engagements/$ENGAGEMENT_ID/audit-runs?upload_id=$UPLOAD_ID" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```
Then copy `id` from that response as `RUN_ID` and inspect:
```bash
curl -sS "http://127.0.0.1:8000/api/v1/audit-runs/$RUN_ID/findings" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

## Scope and caveats
- Phase 3A only supports sales_register.
- Out-of-period dates are screening exceptions, not proof of misstatement.
- The current source register has 3 rows, so this validates the workflow only; use labelled synthetic fixtures for evaluation.
- This overlay does not yet implement Groq dynamic code generation. That is the next separate deliverable and must run generated code in an isolated, no-network worker. Never execute Groq output with `exec()` inside FastAPI.
