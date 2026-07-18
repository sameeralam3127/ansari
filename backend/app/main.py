"""FastAPI entry point for the ANSARI backend."""

from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="ANSARI", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
