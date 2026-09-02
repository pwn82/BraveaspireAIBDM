"""ai gateway tracking columns

Phase 6 additions to ai_logs: status, error, token counts, cost, injection flag.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("status",             sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("error",              sa.Text(),            nullable=True))
        batch_op.add_column(sa.Column("input_tokens",       sa.Integer(),         nullable=True))
        batch_op.add_column(sa.Column("output_tokens",      sa.Integer(),         nullable=True))
        batch_op.add_column(sa.Column("cost_micro_usd",     sa.Integer(),         nullable=True))
        batch_op.add_column(sa.Column("contains_untrusted", sa.Boolean(),         nullable=True,
                                      server_default=sa.text("0")))
        batch_op.create_index(batch_op.f("ix_ai_logs_status"), ["status"], unique=False)
        batch_op.create_index("ix_ai_logs_org_created", ["organization_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_logs_org_created")
        batch_op.drop_index(batch_op.f("ix_ai_logs_status"))
        batch_op.drop_column("contains_untrusted")
        batch_op.drop_column("cost_micro_usd")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("error")
        batch_op.drop_column("status")
