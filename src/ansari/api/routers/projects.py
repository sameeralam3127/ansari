import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ansari.api.db import get_db
from ansari.api.models import Project
from ansari.api.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    if db.scalar(select(Project).where(Project.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="project name already exists")
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project)))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    db.delete(project)
    db.commit()
