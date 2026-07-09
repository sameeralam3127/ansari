"""Shared data models for ANSARI reliability checks."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Supported health states for a checked resource."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ResourceHealth(BaseModel):
    """Normalized result returned by a reliability check."""

    resource_name: str
    resource_type: str
    status: HealthStatus
    message: str
    signals: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
