"""production hot-path indexes

Composite (organization_id, X) indexes for the query patterns the app runs
most often — tenant list/search on Contact.email, filter by Status on
Company/Outreach, scheduler scan for overdue Outreach.next_followup_at, and
sorted list of FollowUp by scheduled_at within an org.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, columns, unique)
_INDEXES = [
    # Contact lookup by email inside a tenant (most common list/search query).
    ("ix_contacts_org_email",       "contacts",  ["organization_id", "email"],           False),
    # Pipeline dashboards filter Company by status inside a tenant.
    ("ix_companies_org_status",     "companies", ["organization_id", "status"],          False),
    # Outreach page filters by status per org.
    ("ix_outreach_org_status",      "outreach",  ["organization_id", "status"],          False),
    # Recent-companies list per org.
    ("ix_companies_org_created",    "companies", ["organization_id", "created_at"],      False),
    # Scheduler sweeps for overdue follow-ups; scan by next_followup_at.
    ("ix_outreach_next_followup",   "outreach",  ["next_followup_at"],                    False),
    # Follow-ups page: ordered by scheduled_at within a status filter, per org.
    ("ix_followups_org_status_sch", "followups", ["organization_id", "status", "scheduled_at"], False),
]


def upgrade() -> None:
    for name, table, cols, unique in _INDEXES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_index(name, cols, unique=unique)


def downgrade() -> None:
    for name, table, _cols, _unique in reversed(_INDEXES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(name)
