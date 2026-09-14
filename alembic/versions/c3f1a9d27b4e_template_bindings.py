"""template bindings: the fleet's cached view of each repo's manifest

Revision ID: c3f1a9d27b4e
Revises: b1c4e7f92a30
Create Date: 2026-09-14

One row per template attached to a project's repo, so a repo carrying two
templates has two rows and fleet-wide drift can be answered without cloning
every repo. The manifest committed in the repo stays authoritative.

`position` keeps manifest order and, with `project_id`, is unique: the same
template may be attached twice, but not twice at the same place. `project_id`
and `template` are indexed because both are fleet-query filters, and Postgres
does not index foreign keys on its own.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import ansari.api.models

revision: str = "c3f1a9d27b4e"
down_revision: str | None = "b1c4e7f92a30"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_bindings",
        sa.Column("id", ansari.api.models.UUID(), nullable=False),
        sa.Column("project_id", ansari.api.models.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("behind", sa.Boolean(), nullable=False),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.Column("unresolved", sa.Boolean(), nullable=False),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "position", name="uq_template_bindings_project_position"),
    )
    op.create_index(op.f("ix_template_bindings_project_id"), "template_bindings", ["project_id"])
    op.create_index(op.f("ix_template_bindings_template"), "template_bindings", ["template"])


def downgrade() -> None:
    op.drop_index(op.f("ix_template_bindings_template"), table_name="template_bindings")
    op.drop_index(op.f("ix_template_bindings_project_id"), table_name="template_bindings")
    op.drop_table("template_bindings")
