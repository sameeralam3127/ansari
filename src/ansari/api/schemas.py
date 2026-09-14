import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class PipelineStatusUpdate(BaseModel):
    """Body for `PATCH /pipelines/{id}/status`.

    A query parameter would put a state-changing value into access logs and
    proxy caches, so the new status travels in the body.
    """

    status: PipelineStatus


class TemplateBindingWrite(BaseModel):
    """One `templates:` entry from a repo's manifest, with its drift as last checked.

    `rendered_at` must carry a timezone: a naive value would be stored against
    whatever the database session assumes, the defect fixed in #19.
    """

    template: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    rendered_at: AwareDatetime
    files: dict[str, str]
    behind: bool = False
    edited: bool = False
    unresolved: bool = False


class TemplateBindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    position: int
    template: str
    version: str
    rendered_at: datetime
    files: dict[str, str]
    behind: bool
    edited: bool
    unresolved: bool
    reported_at: datetime
