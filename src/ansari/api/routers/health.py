from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ansari.api.db import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return {"status": "ok"}
