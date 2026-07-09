"""Base interface for pluggable resource checkers."""

from abc import ABC, abstractmethod

from ansari.models import ResourceHealth


class Checker(ABC):
    """A single-responsibility check for one class of infrastructure resource."""

    @abstractmethod
    def matches(self, resource_name: str) -> bool:
        """Return True if this checker knows how to check the given resource name."""

    @abstractmethod
    def check(self, resource_name: str) -> ResourceHealth:
        """Run the check and return a normalized ResourceHealth result."""
