import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.errors import api_error
from app.db.session import get_db
from app.models.engagement import Engagement, EngagementMembership
from app.models.identity import User
from app.models.ingestion import SourceUpload, IngestionJob, SourceRecord
from app.services.ingestion import SUPPORTED, file_sha256, read_table, suggest_mapping, validate_rows, canonicalize

router = APIRouter()
UPLOAD_ROOT = Path("uploads")
MAX_PREVIEW_ROWS = 100

def now():
    return datetime.now(timezone.utc)

def get_upload_or_404(db: Session, upload_id: str) -> SourceUpload:
    item = db.query(SourceUpload).filter_by(id=upload_id).first()
    if not item:
        raise api_error(404, "UPLOAD_NOT_FOUND", "Upload was not found.")
    return item

def ensure_engagement_access(db: Session, user: User, engagement_id: str):
    engagement = db.query(Engagement).filter_by(id=engagement_id).first()
    if not engagement:
        raise api_error(404, "ENGAGEMENT_NOT_FOUND", "Engagement was not found.")
    if user.role != "ADMIN" and not db.query(EngagementMembership).filter_by(engagement_id=engagement_id, user_id=user.id).first():
        raise api_error(403, "ENGAGEMENT_ACCESS_DENIED", "You do not have access to this engagement.")
    return engagement

def ensure_upload_access(db: Session, user: User, item: SourceUpload):
    ensure_engagement_access(db, user, item.engagement_id)

def upload_public(item: SourceUpload) -> dict[str, Any]:
    return {"id": item.id, "engagement_id": item.engagement_id, "original_filename": item.original_filename,
        "extension": item.extension, "content_type": item.content_type, "size_bytes": item.size_bytes,
        "sha256": item.sha256, "dataset_type": item.dataset_type, "status": item.status,
        "row_count": item.row_count, "created_at": item.created_at.isoformat(),
        "validation_summary": json.loads(item.validation_summary) if item.validation_summary else None}

def parse_upload(item: SourceUpload):
    ensure_tabular_upload(item)
    headers, rows = read_table(Path(item.stored_path))
    mapping = json.loads(item.column_mapping_json) if item.column_mapping_json else suggest_mapping(headers)
    return headers, rows, mapping

def ensure_tabular_upload(item: SourceUpload):
    if Path(item.stored_path).suffix.lower() not in SUPPORTED or item.dataset_type == "supporting_document":
        raise api_error(415, "TABULAR_FILE_REQUIRED", "This supporting document cannot be validated or ingested as a table.")

@router.post("/engagements/{engagement_id}/uploads", status_code=201)
def create_upload(engagement_id: str, file: UploadFile = File(...), dataset_type: str = Form("sales_register"),
                  user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    ensure_engagement_access(db, user, engagement_id)
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if dataset_type not in {"sales_register", "customer_master", "general_ledger", "dispatch_register", "credit_notes", "generic", "supporting_document"}:
        raise api_error(422, "INVALID_DATASET_TYPE", "Unsupported dataset_type.")
    if suffix == ".pdf" and dataset_type != "supporting_document":
        raise api_error(415, "DOCUMENT_DATASET_TYPE_REQUIRED", "PDF files must use dataset_type=supporting_document.")
    if suffix in SUPPORTED and dataset_type == "supporting_document":
        raise api_error(422, "TABULAR_DATASET_TYPE_REQUIRED", "CSV and XLSX files must use a tabular dataset type.")
    if suffix not in SUPPORTED and not (suffix == ".pdf" and dataset_type == "supporting_document"):
        raise api_error(415, "UNSUPPORTED_FILE_TYPE", "Supported uploads are CSV, XLSX, and PDF supporting documents.")
    data = file.file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if not data:
        raise api_error(400, "EMPTY_FILE", "Uploaded file is empty.")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise api_error(413, "FILE_TOO_LARGE", f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    upload_id = str(uuid.uuid4())
    directory = UPLOAD_ROOT / engagement_id
    directory.mkdir(parents=True, exist_ok=True)
    stored_path = directory / f"{upload_id}{suffix}"
    stored_path.write_bytes(data)
    digest = file_sha256(stored_path)
    item = SourceUpload(id=upload_id, engagement_id=engagement_id, uploaded_by=user.id,
        original_filename=filename, stored_path=str(stored_path.resolve()), extension=suffix,
        content_type=file.content_type or "application/octet-stream", size_bytes=len(data), sha256=digest,
        dataset_type=dataset_type, status="UPLOADED")
    db.add(item)
    db.commit()
    db.refresh(item)
    return upload_public(item)

@router.get("/engagements/{engagement_id}/uploads")
def list_uploads(engagement_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_engagement_access(db, user, engagement_id)
    query = db.query(SourceUpload).filter_by(engagement_id=engagement_id).order_by(SourceUpload.created_at.desc())
    total = query.count()
    items = query.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [upload_public(x) for x in items], "page": page, "page_size": page_size, "total": total}

@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    return upload_public(item)

@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: str, user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    if db.query(SourceRecord).filter_by(upload_id=item.id).first():
        raise api_error(409, "UPLOAD_ALREADY_INGESTED", "An upload with ingested source records cannot be deleted in this phase.")
    path = Path(item.stored_path)
    db.query(IngestionJob).filter_by(upload_id=item.id).delete()
    db.delete(item); db.commit()
    path.unlink(missing_ok=True)
    return None

@router.post("/uploads/{upload_id}/validate")
def validate_upload(upload_id: str, user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    ensure_tabular_upload(item)
    if db.query(SourceRecord).filter_by(upload_id=item.id).first():
        raise api_error(409, "UPLOAD_ALREADY_INGESTED", "This upload has already been ingested.")
    headers, rows = read_table(Path(item.stored_path))
    mapping = json.loads(item.column_mapping_json) if item.column_mapping_json else suggest_mapping(headers)
    result = validate_rows(rows, mapping, item.dataset_type)
    item.row_count = len(rows); item.status = "VALIDATED" if result["valid"] else "VALIDATION_FAILED"
    item.validation_summary = json.dumps(result, default=str)
    if not item.column_mapping_json:
        item.column_mapping_json = json.dumps(mapping)
    db.commit()
    return {"upload_id": item.id, "status": item.status, "columns": headers, "suggested_mapping": mapping, **result}

@router.get("/uploads/{upload_id}/validation")
def get_validation(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    return {"upload_id": item.id, "status": item.status,
            "validation": json.loads(item.validation_summary) if item.validation_summary else None}

@router.get("/uploads/{upload_id}/columns")
def get_columns(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    headers, rows, mapping = parse_upload(item)
    return {"upload_id": item.id, "columns": headers, "suggested_mapping": mapping, "row_count": len(rows)}

@router.get("/uploads/{upload_id}/preview")
def preview_upload(upload_id: str, limit: int = Query(20, ge=1, le=MAX_PREVIEW_ROWS),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    headers, rows, mapping = parse_upload(item)
    return {"upload_id": item.id, "columns": headers, "mapping": mapping, "row_count": len(rows), "items": rows[:limit]}

@router.get("/uploads/{upload_id}/mappings")
def get_mapping(upload_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    headers, _, mapping = parse_upload(item)
    return {"upload_id": item.id, "mapping": mapping, "available_columns": headers}

@router.put("/uploads/{upload_id}/mappings")
def put_mapping(upload_id: str, body: dict[str, str], user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    if db.query(SourceRecord).filter_by(upload_id=item.id).first():
        raise api_error(409, "UPLOAD_ALREADY_INGESTED", "Column mapping cannot change after ingestion.")
    headers, _, _ = parse_upload(item)
    if any(source not in headers for source in body.values()):
        raise api_error(422, "MAPPING_COLUMN_NOT_FOUND", "Every mapped source column must exist in the uploaded file.")
    allowed = {"invoice_number", "invoice_date", "customer_name", "total_amount", "taxable_value", "tax_amount"}
    if set(body) - allowed:
        raise api_error(422, "UNKNOWN_CANONICAL_FIELD", "Mapping contains unsupported canonical fields.")
    item.column_mapping_json = json.dumps(body)
    item.status = "UPLOADED"; item.validation_summary = None
    db.commit()
    return {"upload_id": item.id, "mapping": body, "status": item.status}

@router.post("/uploads/{upload_id}/ingest", status_code=202)
def ingest_upload(upload_id: str, user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    if db.query(SourceRecord).filter_by(upload_id=item.id).first():
        raise api_error(409, "UPLOAD_ALREADY_INGESTED", "This upload has already been ingested; duplicate ingestion is blocked.")
    headers, rows, mapping = parse_upload(item)
    validation = validate_rows(rows, mapping, item.dataset_type)
    item.row_count = len(rows); item.validation_summary = json.dumps(validation, default=str)
    if not validation["valid"]:
        item.status = "VALIDATION_FAILED"; db.commit()
        raise api_error(422, "UPLOAD_VALIDATION_FAILED", "Fix the reported validation errors before ingestion.", validation["errors"][:100])
    job = IngestionJob(engagement_id=item.engagement_id, upload_id=item.id, requested_by=user.id,
        status="RUNNING", stage="persisting_records", message="Persisting validated source rows", started_at=now())
    db.add(job); db.flush()
    try:
        for row_number, row in enumerate(rows, start=2):
            record = canonicalize(row, mapping)
            db.add(SourceRecord(upload_id=item.id, engagement_id=item.engagement_id, dataset_type=item.dataset_type,
                source_row_number=row_number, record_json=json.dumps(record, default=str, ensure_ascii=False)))
        job.status = "SUCCEEDED"; job.stage = "complete"; job.message = f"Ingested {len(rows)} source rows."; job.finished_at = now()
        item.status = "INGESTED"
        db.commit()
    except Exception:
        db.rollback()
        item = get_upload_or_404(db, upload_id)
        job = IngestionJob(engagement_id=item.engagement_id, upload_id=item.id, requested_by=user.id,
            status="FAILED", stage="persisting_records", message="Ingestion failed; no records were committed.", started_at=now(), finished_at=now())
        item.status = "INGESTION_FAILED"; db.add(job); db.commit()
        raise api_error(500, "INGESTION_FAILED", "Ingestion failed. No source records were committed; inspect server logs and retry.")
    return {"job_id": job.id, "upload_id": item.id, "status": job.status, "row_count": len(rows), "message": job.message}

@router.post("/uploads/{upload_id}/retry", status_code=202)
def retry_upload(upload_id: str, user: User = Depends(require_roles("ADMIN", "CLIENT_EMPLOYEE")), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, upload_id); ensure_upload_access(db, user, item)
    if db.query(SourceRecord).filter_by(upload_id=item.id).first():
        raise api_error(409, "UPLOAD_ALREADY_INGESTED", "This upload has already been ingested.")
    return ingest_upload(upload_id, user, db)

@router.get("/engagements/{engagement_id}/ingestion-jobs")
def list_ingestion_jobs(engagement_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_engagement_access(db, user, engagement_id)
    query = db.query(IngestionJob).filter_by(engagement_id=engagement_id).order_by(IngestionJob.created_at.desc())
    total = query.count(); items = query.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": x.id, "upload_id": x.upload_id, "status": x.status, "stage": x.stage,
        "message": x.message, "created_at": x.created_at.isoformat(), "started_at": x.started_at.isoformat() if x.started_at else None,
        "finished_at": x.finished_at.isoformat() if x.finished_at else None} for x in items], "page": page, "page_size": page_size, "total": total}

@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(IngestionJob).filter_by(id=job_id).first()
    if not job: raise api_error(404, "JOB_NOT_FOUND", "Job was not found.")
    ensure_engagement_access(db, user, job.engagement_id)
    return {"id": job.id, "upload_id": job.upload_id, "engagement_id": job.engagement_id, "status": job.status,
            "stage": job.stage, "message": job.message, "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None}

@router.get("/datasets/{dataset_id}/records")
def get_dataset_records(dataset_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = get_upload_or_404(db, dataset_id); ensure_upload_access(db, user, item)
    query = db.query(SourceRecord).filter_by(upload_id=item.id).order_by(SourceRecord.source_row_number.asc())
    total = query.count(); records = query.offset((page-1)*page_size).limit(page_size).all()
    return {"items": [{"id": r.id, "upload_id": r.upload_id, "engagement_id": r.engagement_id,
        "dataset_type": r.dataset_type, "source_row_number": r.source_row_number,
        "record": json.loads(r.record_json), "created_at": r.created_at.isoformat()} for r in records],
        "page": page, "page_size": page_size, "total": total}
