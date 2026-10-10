from fastapi import HTTPException

def api_error(status_code: int, code: str, message: str, details: list | None = None):
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": details or []})
