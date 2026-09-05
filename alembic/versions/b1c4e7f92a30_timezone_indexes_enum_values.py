"""timezone-aware timestamps, foreign-key indexes, lowercase enum values

Revision ID: b1c4e7f92a30
Revises: 440544c930c1
Create Date: 2026-09-05

Three defects fixed together because they all touch the same columns:

1. Timestamps were ``TIMESTAMP WITHOUT TIME ZONE`` while the application writes
   ``datetime.now(UTC)``. Postgres silently dropped the offset, so any value
   written outside UTC was wrong. Existing rows were written as UTC, so the
   conversion below states that explicitly rather than assuming server local
   time.
2. Foreign keys had no indexes. Postgres does not create them automatically,
   and every one of these columns is a filter target.
3. Enums stored member names (``PENDING``) while the API served values
   (``pending``), so direct SQL saw different data than the API.

Postgres-specific: ``ALTER TYPE ... RENAME VALUE`` has no SQLite equivalent,
and this project's database is Postgres.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c4e7f92a30"
down_revision: str | None = "440544c930c1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TIMESTAMPS: list[tuple[str, str, bool]] = [
    ("projects", "created_at", False),
    ("pipeline_runs", "started_at", False),
    ("pipeline_runs", "finished_at", True),
    ("deployments", "deployed_at", False),
]

_FK_INDEXES: list[tuple[str, str]] = [
    ("environments", "project_id"),
    ("pipeline_runs", "project_id"),
    ("deployments", "environment_id"),
    ("deployments", "pipeline_run_id"),
]

_ENUM_VALUES: list[tuple[str, list[str]]] = [
    ("pipeline_status", ["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]),
    ("deployment_status", ["PENDING", "DEPLOYING", "HEALTHY", "FAILED", "ROLLED_BACK"]),
]


def upgrade() -> None:
    for table, column, nullable in _TIMESTAMPS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )

    for table, column in _FK_INDEXES:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column])

    for type_name, names in _ENUM_VALUES:
        for name in names:
            op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{name}' TO '{name.lower()}'")


def downgrade() -> None:
    for type_name, names in _ENUM_VALUES:
        for name in names:
            op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{name.lower()}' TO '{name}'")

    for table, column in _FK_INDEXES:
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)

    for table, column, nullable in _TIMESTAMPS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
