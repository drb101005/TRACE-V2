from fastapi import APIRouter
from app.api.v1.endpoints import auth, engagements, organizations, uploads, ai_audit, audits

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(engagements.router, prefix="/engagements", tags=["Engagements"])
api_router.include_router(uploads.router, tags=["Uploads and Ingestion"])

api_router.include_router(audits.router, tags=["Audit Engine"])

api_router.include_router(ai_audit.router, prefix="/ai-audit", tags=["AI Audit"])

from app.api.v1.endpoints import ai_execution
api_router.include_router(ai_execution.router, prefix="/ai-audit", tags=["AI Audit Execution"])


from app.api.v1.endpoints import reconciliation
api_router.include_router(reconciliation.router, prefix="/ai-audit", tags=["Financial Reconciliation"])


from app.api.v1.endpoints import sampling
api_router.include_router(sampling.router, prefix="/ai-audit", tags=["Risk Scoring & Sampling"])


from app.api.v1.endpoints import evidence
api_router.include_router(evidence.router, prefix="/ai-audit", tags=["Evidence Management"])
from app.api.v1.endpoints import evidence_links
api_router.include_router(evidence_links.router, prefix="/ai-audit", tags=["Evidence Links"])
from app.api.v1.endpoints import findings
api_router.include_router(findings.router, prefix="/ai-audit", tags=["Findings Management"])

from app.api.v1.endpoints import audit_trail
api_router.include_router(audit_trail.router, prefix="/ai-audit", tags=["Audit Trail"])

from app.api.v1.endpoints import workpaper
api_router.include_router(workpaper.router, tags=["Audit Workpapers"])
