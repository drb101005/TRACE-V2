from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.endpoints.uploads import (
    get_upload_or_404,
    ensure_upload_access,
    parse_upload,
)
from app.db.session import get_db
from app.models.identity import User
from app.services.groq_audit import generate_audit_script

router = APIRouter()


class ScriptRequest(BaseModel):
    upload_id: str
    objective: str = Field(min_length=10, max_length=1000)


@router.post("/generate-script")
def generate_script(
    body: ScriptRequest,
    user: User = Depends(
        require_roles("ADMIN", "INDEPENDENT_AUDITOR", "HUMAN_AUDITOR")
    ),
    db: Session = Depends(get_db),
):
    upload = get_upload_or_404(db, body.upload_id)
    ensure_upload_access(db, user, upload)

    headers, rows, mapping = parse_upload(upload)
    if not rows:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Dataset contains no rows.")

    script = generate_audit_script(
        objective=body.objective,
        columns=headers,
    )

    return {
        "upload_id": upload.id,
        "dataset_type": upload.dataset_type,
        "row_count": len(rows),
        "columns": headers,
        "objective": body.objective,
        "generated_script": script,
        "execution_status": "NOT_EXECUTED",
        "message": "AI-generated proposal only. Review before execution.",
    }
