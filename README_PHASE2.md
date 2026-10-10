# TRACE-V2 — Phase 2 overlay: uploads and ingestion

This is an **overlay patch** for the Phase 1 FastAPI project. It preserves existing auth, roles, organizations, and engagement APIs. Apply it at the root of your existing `TRACE-V2` repository.

## Implemented

- Multipart CSV/XLSX upload with extension, size, and empty-file checks.
- SHA-256 hash of original upload; original bytes preserved under `uploads/<engagement_id>/`.
- Engagement-scoped authorization.
- Header detection, suggested canonical column mappings, preview, and mapping updates.
- Row-level validation for sales-register required fields, missing invoice numbers/dates/amounts, duplicate invoice numbers, and invalid decimal amounts.
- Ingestion jobs with statuses and query endpoint.
- Persisted source rows linked to the original upload and source row number.
- Duplicate ingestion is blocked; ingestion never locks a dataset automatically.
- Basic helper tests.

## Current scope / limitations

- This phase accepts **CSV and XLSX**, as specified in the API contract. PaddleOCR for scanned invoice/PDF evidence should be added as a separate document-evidence pipeline; OCR output must never be treated as verified financial truth without review.
- Job execution is synchronous inside the request for this MVP, but a job record/status is exposed. A proper worker queue can replace this later.
- `uploads/` contains client financial data. Keep it out of Git and protect it with filesystem permissions. This local SQLite implementation is for development/demo, not production deployment.
- Dataset registration/versioning/submission locking are not yet implemented in this phase.

## Apply patch

From the root of your existing repository:

```bash
unzip ~/Downloads/trace_v2_phase2_overlay.zip -d /tmp/trace-v2-phase2
cp -a /tmp/trace-v2-phase2/. .
```

If your downloaded file is in a different folder, update the `unzip` path. Inspect `git status` before continuing.

Then activate your environment and install dependencies:

```bash
source .venv/bin/activate
pip install -r requirements-phase2.txt
```

Add this to `.gitignore` if it is not already present:

```gitignore
uploads/
*.db
.env
```

Restart Uvicorn (stop the current process with Ctrl+C first):

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Authenticate using the Authorize button with a bearer token from `/api/v1/auth/login`.

## Demo workflow

1. Log in as `client@example.com` to upload; use the seeded demo engagement ID from `python -m app.seed`.
2. `POST /api/v1/engagements/{engagement_id}/uploads` with `file` and `dataset_type=sales_register`.
3. `GET /api/v1/uploads/{upload_id}/columns` to inspect headers and suggested mappings.
4. `POST /api/v1/uploads/{upload_id}/validate` and fix any row-level issues.
5. Optionally `PUT /api/v1/uploads/{upload_id}/mappings` with a JSON object mapping canonical fields to exact source column names, then validate again.
6. `POST /api/v1/uploads/{upload_id}/ingest` only after validation succeeds.
7. Check `GET /api/v1/jobs/{job_id}` and `GET /api/v1/datasets/{upload_id}/records`.

Canonical mapping example:

```json
{
  "invoice_number": "Invoice No.",
  "invoice_date": "Invoice Date",
  "customer_name": "Customer Name",
  "total_amount": "Grand Total",
  "taxable_value": "Taxable Value",
  "tax_amount": "GST Amount"
}
```

All amounts are parsed with Python `Decimal` and stored as strings in canonical JSON; no binary float is used for authoritative financial values.
