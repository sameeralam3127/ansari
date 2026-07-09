from ansari.modules.checkers import DEFAULT_CHECKERS
from ansari.modules.checkers.base import Checker


def test_default_checkers_are_checker_instances() -> None:
    assert DEFAULT_CHECKERS
    assert all(isinstance(checker, Checker) for checker in DEFAULT_CHECKERS)


def test_default_checkers_cover_every_documented_resource_type() -> None:
    resource_types = {
        checker.check("probe").resource_type for checker in DEFAULT_CHECKERS
    }

    assert resource_types == {
        "kubernetes-cluster",
        "kubernetes-pod",
        "database",
        "terraform-state",
    }
