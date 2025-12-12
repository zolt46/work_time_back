# File: /backend/app/routers/system.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """간단한 DB 연결 헬스체크 엔드포인트."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - runtime safety
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from exc
    return {"db_status": "ok"}
