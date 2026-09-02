"""tasks table — dashboard "My Tasks" panel

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("related_type", sa.String(length=20), nullable=True),
        sa.Column("related_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index("ix_tasks_id", ["id"], unique=False)
        batch_op.create_index("ix_tasks_organization_id", ["organization_id"], unique=False)
        batch_op.create_index("ix_tasks_assigned_to_id", ["assigned_to_id"], unique=False)
        batch_op.create_index("ix_tasks_org_status_due", ["organization_id", "status", "due_date"], unique=False)
        batch_op.create_index("ix_tasks_org_assignee", ["organization_id", "assigned_to_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_tasks_org_assignee")
        batch_op.drop_index("ix_tasks_org_status_due")
        batch_op.drop_index("ix_tasks_assigned_to_id")
        batch_op.drop_index("ix_tasks_organization_id")
        batch_op.drop_index("ix_tasks_id")
    op.drop_table("tasks")
