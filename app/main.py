from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.db.session import init_db, engine
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version="0.3.0",
    description="TRACE-V2 Phase 3A: deterministic sales-register audit engine.",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error = {"code": detail["code"], "message": detail["message"],
                 "request_id": request.headers.get("x-request-id", "untracked"),
                 "details": detail.get("details", [])}
    else:
        error = {"code": "HTTP_ERROR", "message": str(detail),
                 "request_id": request.headers.get("x-request-id", "untracked"), "details": []}
    return JSONResponse(status_code=exc.status_code, content={"error": error}, headers=exc.headers)

@app.get("/health", tags=["Platform"])
def health():
    return {"status": "ok"}

@app.get("/ready", tags=["Platform"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "reachable"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})

@app.get("/api/v1/metadata", tags=["Platform"])
def metadata():
    return {"api_version": "v1", "application": settings.APP_NAME, "phase": 3,
        "implemented_capabilities": ["health", "readiness", "authentication", "role_permissions", "organizations", "engagements", "csv_xlsx_uploads", "pdf_supporting_document_uploads", "file_hashing", "column_mapping", "row_validation", "ingestion_jobs", "source_records", "deterministic_sales_register_audit", "reconciliation", "risk_sampling", "cutoff_testing", "audit_runs", "traceable_findings", "finding_review", "evidence_metadata", "evidence_verification", "audit_trail_verification", "workpaper_export"],
        "planned_capabilities": ["groq_dynamic_pandas_execution", "ocr_document_extraction", "dataset_versioning", "submissions_and_locking", "engagement_signoff", "change_impact", "mcp"]}

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
