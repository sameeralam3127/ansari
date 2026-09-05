import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ansari.api.db import get_db
from ansari.api.models import Deployment, DeploymentStatus, Environment, PipelineRun
from ansari.api.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ansari.api.schemas import DeploymentCreate, DeploymentRead

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.post("", response_model=DeploymentRead, status_code=status.HTTP_201_CREATED)
def create_deployment(payload: DeploymentCreate, db: Session = Depends(get_db)) -> Deployment:
    if db.get(Environment, payload.environment_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="environment not found")
    if db.get(PipelineRun, payload.pipeline_run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pipeline run not found")
    deployment = Deployment(**payload.model_dump())
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


@router.get("", response_model=list[DeploymentRead])
def list_deployments(
    environment_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[Deployment]:
    stmt = select(Deployment)
    if environment_id is not None:
        stmt = stmt.where(Deployment.environment_id == environment_id)
    # Newest first, with id as a tiebreak: two deployments can share a
    # timestamp, and an unordered LIMIT would page inconsistently.
    stmt = stmt.order_by(Deployment.deployed_at.desc(), Deployment.id).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.post("/{deployment_id}/rollback", response_model=DeploymentRead)
def rollback_deployment(deployment_id: uuid.UUID, db: Session = Depends(get_db)) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="deployment not found")
    deployment.status = DeploymentStatus.ROLLED_BACK
    db.commit()
    db.refresh(deployment)
    return deployment
