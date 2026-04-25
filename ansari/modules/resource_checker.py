"""Backward-compatible imports for the renamed reliability checker module."""

from ansari.modules.reliability_checker import (  # noqa: F401
    HealthStatus,
    ReliabilityChecker,
    ResourceHealth,
)

ResourceChecker = ReliabilityChecker
