import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, Enum, ForeignKey, String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeEngine

from ansari.api.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class UUID(TypeDecorator[uuid.UUID]):
    """Platform-independent UUID: native on Postgres, CHAR(36) elsewhere (e.g. SQLite in tests)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return str(value)
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class PipelineStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DeploymentStatus(enum.StrEnum):
    PENDING = "pending"
    DEPLOYING = "deploying"
    HEALTHY = "healthy"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    repo_url: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    environments: Mapped[list["Environment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(50))
    cluster: Mapped[str] = mapped_column(String(100))
    namespace: Mapped[str] = mapped_column(String(100))

    project: Mapped["Project"] = relationship(back_populates="environments")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="environment", cascade="all, delete-orphan"
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[PipelineStatus] = mapped_column(
        Enum(PipelineStatus, name="pipeline_status"), default=PipelineStatus.PENDING
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    project: Mapped["Project"] = relationship(back_populates="pipeline_runs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id"))
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    image_tag: Mapped[str] = mapped_column(String(200))
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status"), default=DeploymentStatus.PENDING
    )
    deployed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    environment: Mapped["Environment"] = relationship(back_populates="deployments")
