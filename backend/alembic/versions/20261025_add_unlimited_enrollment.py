"""Allow new unbounded registration tickets without altering legacy quotas.

Revision ID: 20261025_unlimited_enroll
Revises: 20261025_agent_lifecycle
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_unlimited_enroll"
down_revision = "20261025_agent_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve existing ticket checks/claims and avoid rebuilding a referenced
    # SQLite table. used_count remains the legacy bounded-quota counter; exact
    # registration history for unlimited tickets lives in their claim records.
    op.add_column("auto_enrollment_tickets", sa.Column("unlimited", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("auto_enrollment_tickets", "unlimited")
