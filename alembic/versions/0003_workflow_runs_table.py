"""workflow_runs table

Phase 4 — durable idempotency + retry ledger for background jobs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("workflow_name", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=True, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workflow_runs_id"),              ["id"],              unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_organization_id"), ["organization_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_workflow_name"),   ["workflow_name"],   unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_next_retry_at"),   ["next_retry_at"],   unique=False)
        # Uniqueness that makes idempotency correct: same (org, workflow, key) can only
        # exist once. Two orgs may independently reuse the same key.
        batch_op.create_index(
            "ix_workflow_runs_org_wf_idempotency",
            ["organization_id", "workflow_name", "idempotency_key"],
            unique=True,
        )
        # Cheap lookup for "give me the next retry candidate":
        batch_op.create_index(
            "ix_workflow_runs_status_next_retry",
            ["status", "next_retry_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_workflow_runs_status_next_retry")
        batch_op.drop_index("ix_workflow_runs_org_wf_idempotency")
        batch_op.drop_index(batch_op.f("ix_workflow_runs_next_retry_at"))
        batch_op.drop_index(batch_op.f("ix_workflow_runs_workflow_name"))
        batch_op.drop_index(batch_op.f("ix_workflow_runs_organization_id"))
        batch_op.drop_index(batch_op.f("ix_workflow_runs_id"))
    op.drop_table("workflow_runs")
