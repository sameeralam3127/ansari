"""Configuration models for ANSARI."""

from pydantic import BaseModel, ConfigDict, Field


class AnsariConfig(BaseModel):
    """Main configuration for ANSARI."""

    model_config = ConfigDict(validate_assignment=True)

    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    timeout: int = Field(
        default=30, description="Default timeout for operations in seconds"
    )


class ResourceConfig(BaseModel):
    """Configuration for resource checks."""

    model_config = ConfigDict(validate_assignment=True)

    name: str = Field(..., description="Resource name")
    type: str = Field(..., description="Resource type (eks, ec2, k8s, etc.)")
    region: str | None = Field(default=None, description="Cloud region")
    namespace: str | None = Field(default=None, description="Kubernetes namespace")


config = AnsariConfig()
