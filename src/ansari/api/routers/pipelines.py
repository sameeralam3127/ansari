import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ansari.api.db import get_db
from ansari.api.models import PipelineRun, PipelineStatus, Project
from ansari.api.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ansari.api.schemas import PipelineRunCreate, PipelineRunRead, PipelineStatusUpdate

router = APIRouter(prefix="/projects/{project_id}/pipelines", tags=["pipelines"])


@router.post("", response_model=PipelineRunRead, status_code=status.HTTP_201_CREATED)
def trigger_pipeline(
    project_id: uuid.UUID, payload: PipelineRunCreate, db: Session = Depends(get_db)
) -> PipelineRun:
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    run = PipelineRun(project_id=project_id, commit_sha=payload.commit_sha)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=list[PipelineRunRead])
def list_pipeline_runs(
    project_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[PipelineRun]:
    stmt = (
        select(PipelineRun)
        .where(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.started_at.desc(), PipelineRun.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


@router.patch("/{run_id}/status", response_model=PipelineRunRead)
def update_pipeline_status(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: PipelineStatusUpdate,
    db: Session = Depends(get_db),
) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pipeline run not found")
    run.status = payload.status
    if payload.status in (PipelineStatus.SUCCEEDED, PipelineStatus.FAILED):
        run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    return run
