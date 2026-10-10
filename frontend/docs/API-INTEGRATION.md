# Frontend and backend integration

The client uses `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). It authenticates with `/auth/login`, verifies the session with `/auth/me`, and sends bearer tokens on protected requests.

The workspace calls the backend for organizations, engagements, uploads, validation, ingestion, previews, mappings, audit runs and findings, reconciliation, risk sampling, evidence metadata and verification, audit-trail verification, and workpaper export. File bytes are transmitted using multipart `FormData`.

## Upload formats

- CSV and XLSX are stored, hashed, and can be validated and ingested as tabular datasets.
- PDF is stored and hashed as `supporting_document`; it cannot be validated or ingested as a table.
- The backend enforces the upload size limit and access roles. Upload success is shown only after the API returns successfully.

Engagement sign-off is not presented as an available action because the backend has no sign-off endpoint. Reconciliation results and audit outputs are rendered from backend responses. The backend OpenAPI document remains authoritative for contracts.
