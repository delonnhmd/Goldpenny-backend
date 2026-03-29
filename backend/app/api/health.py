"""Health endpoints for app and database connectivity checks."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Basic app liveness check."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    """Database connectivity check using a minimal SQL query."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "database connected"}
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "database error",
                "error": str(exc),
            },
        )

