"""
Example: add a custom ANSARI checker without touching the built-in modules.

This demonstrates the extension point every real integration (AWS, GCP,
Terraform Cloud, PagerDuty, ...) will eventually use: implement `Checker`,
then hand it to `ReliabilityChecker(checkers=...)` alongside (or instead of)
the bundled demo checkers.

Run it with:
    poetry run python examples/custom_checker.py payments-lambda-fn
"""

import sys

from ansari.models import HealthStatus, ResourceHealth
from ansari.modules.checkers import DEFAULT_CHECKERS
from ansari.modules.checkers.base import Checker
from ansari.modules.reliability_checker import ReliabilityChecker


class LambdaChecker(Checker):
    """Demo checker for AWS Lambda functions."""

    def matches(self, resource_name: str) -> bool:
        return "lambda" in resource_name

    def check(self, resource_name: str) -> ResourceHealth:
        return ResourceHealth(
            resource_name=resource_name,
            resource_type="aws-lambda",
            status=HealthStatus.HEALTHY,
            message="Function has no recent error spikes or throttles.",
            signals={
                "error_rate_5xx": "0.0%",
                "throttles": 0,
                "cold_starts": "low",
            },
            recommendations=[
                "Confirm reserved concurrency covers expected peak traffic.",
                "Check CloudWatch alarms for duration approaching timeout.",
            ],
        )


def build_registry() -> tuple[Checker, ...]:
    """Compose the built-in checkers with the new custom one."""
    return (*DEFAULT_CHECKERS, LambdaChecker())


def main() -> None:
    resource_name = sys.argv[1] if len(sys.argv) > 1 else "payments-lambda-fn"
    checker = ReliabilityChecker(checkers=build_registry())
    health = checker.check_resource(resource_name)
    checker.display_health(health)


if __name__ == "__main__":
    main()
