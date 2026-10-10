# TRACE Revenue Assurance

TRACE provides a FastAPI backend and React frontend for revenue assurance engagements, source-file ingestion, reconciliation, audit testing, findings, evidence metadata, audit-trail verification, and workpaper export.

## Start the backend

Python 3.11 or 3.12 is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Create .env from .env.example if you do not already have local settings.
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs
Health: http://127.0.0.1:8000/health
Readiness: http://127.0.0.1:8000/ready

Seeded local accounts use password `DemoPass123!`:

- `admin@example.com`
- `client@example.com`
- `auditor@example.com`
- `reviewer@example.com`

## Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000/api/v1`. Set `VITE_API_BASE_URL` in `frontend/.env` to change it.

## File handling

- CSV and XLSX files are stored and hashed, then can be mapped, validated, and ingested.
- PDF files are stored and hashed as supporting documents and can have evidence metadata attached.
- The configured `MAX_UPLOAD_MB` limit applies. The API enforces engagement access and role permissions.
- PDF documents are not parsed as tabular data. Engagement sign-off is unavailable because the backend has no sign-off endpoint.

The backend `/docs` and `/openapi.json` describe the active API contracts. Seed credentials are for local development only.
