import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ansari.api.db import get_db
from ansari.api.models import Environment, Project
from ansari.api.schemas import EnvironmentCreate, EnvironmentRead

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["environments"])


@router.post("", response_model=EnvironmentRead, status_code=status.HTTP_201_CREATED)
def create_environment(
    project_id: uuid.UUID, payload: EnvironmentCreate, db: Session = Depends(get_db)
) -> Environment:
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    env = Environment(project_id=project_id, **payload.model_dump())
    db.add(env)
    db.commit()
    db.refresh(env)
    return env


@router.get("", response_model=list[EnvironmentRead])
def list_environments(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Environment]:
    return list(db.scalars(select(Environment).where(Environment.project_id == project_id)))
