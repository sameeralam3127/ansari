import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
)
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


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum values rather than member names.

    SQLAlchemy defaults to storing ``PENDING`` while the API serves ``pending``,
    so anyone querying the database directly sees different data than the API.
    """
    return [str(member.value) for member in enum_cls]


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    environments: Mapped[list["Environment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    template_bindings: Mapped[list["TemplateBinding"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="TemplateBinding.position",
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
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
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[PipelineStatus] = mapped_column(
        Enum(PipelineStatus, name="pipeline_status", values_callable=_enum_values),
        default=PipelineStatus.PENDING,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="pipeline_runs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("environments.id"), index=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    image_tag: Mapped[str] = mapped_column(String(200))
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status", values_callable=_enum_values),
        default=DeploymentStatus.PENDING,
    )
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    environment: Mapped["Environment"] = relationship(back_populates="deployments")


class TemplateBinding(Base):
    """The API's cached view of one template attached to a project's repo.

    One row per `templates:` entry in the repo's `.ansari/manifest.yaml`, so a
    repo carrying two templates has two rows. The manifest in the repo stays
    authoritative; this exists so a fleet question needn't clone every repo.
    """

    __tablename__ = "template_bindings"
    __table_args__ = (
        UniqueConstraint("project_id", "position", name="uq_template_bindings_project_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    """Order in the manifest's `templates:` list; a template may be attached twice."""
    template: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(50))
    rendered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    files: Mapped[dict[str, str]] = mapped_column(JSON)
    """Repo-relative path -> content hash, as recorded in the manifest."""
    behind: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    unresolved: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="template_bindings")
