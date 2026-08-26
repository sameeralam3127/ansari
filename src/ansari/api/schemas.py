import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ansari.api.models import DeploymentStatus, PipelineStatus


class ProjectCreate(BaseModel):
    name: str
    repo_url: str
    language: str


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    repo_url: str
    language: str
    created_at: datetime


class EnvironmentCreate(BaseModel):
    name: str
    cluster: str
    namespace: str


class EnvironmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    cluster: str
    namespace: str


class PipelineRunCreate(BaseModel):
    commit_sha: str


class PipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    commit_sha: str
    status: PipelineStatus
    started_at: datetime
    finished_at: datetime | None


class DeploymentCreate(BaseModel):
    environment_id: uuid.UUID
    pipeline_run_id: uuid.UUID
    image_tag: str


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    environment_id: uuid.UUID
    pipeline_run_id: uuid.UUID
    image_tag: str
    status: DeploymentStatus
    deployed_at: datetime
