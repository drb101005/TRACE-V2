# TRACE frontend

React + Vite client for the TRACE FastAPI backend.

## Run locally

Start the backend from the repository root as described in the root README. Configure the frontend API URL if it differs from the default:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Save this in `frontend/.env`, then run:

```bash
npm install
npm run dev
```

Sign in with an account provisioned by the backend. The access token is held for the browser session and sent as a bearer token for protected requests.

## Backend-connected features

- Authentication and current-user lookup
- Engagement and organization listing; engagement creation for authorized roles
- CSV/XLSX source uploads, server validation, and ingestion
- PDF supporting-document storage and evidence metadata
- Reconciliation, audit runs, findings and permitted human review actions
- Risk based sampling, audit-trail verification and workpaper retrieval

The backend accepts CSV and XLSX as tabular uploads and PDF as supporting documents. The configured backend upload size limit applies. Sign-off remains unavailable because the backend does not expose a sign-off action.

## Build

```bash
npm run build
```
