"""Pluggable resource checkers for ANSARI.

Each checker owns detection (`matches`) and inspection (`check`) for one
class of infrastructure resource. Add a new resource type by writing a
`Checker` subclass and passing it (or a tuple including it) to
`ReliabilityChecker(checkers=...)` -- see `examples/custom_checker.py` for a
worked example.
"""

from ansari.modules.checkers.base import Checker
from ansari.modules.checkers.database import DatabaseChecker
from ansari.modules.checkers.kubernetes import ClusterChecker, PodChecker
from ansari.modules.checkers.terraform import TerraformChecker

DEFAULT_CHECKERS: tuple[Checker, ...] = (
    ClusterChecker(),
    PodChecker(),
    DatabaseChecker(),
    TerraformChecker(),
)

__all__ = [
    "Checker",
    "DEFAULT_CHECKERS",
    "ClusterChecker",
    "PodChecker",
    "DatabaseChecker",
    "TerraformChecker",
]
