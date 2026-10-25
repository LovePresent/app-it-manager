"""Record confirmed removal and independent Windows service health.

Revision ID: 20261025_agent_lifecycle
Revises: 20261025_auto_enrollment
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_agent_lifecycle"
down_revision = "20261025_auto_enrollment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("device_agents", sa.Column("installation_state", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("device_agents", sa.Column("uninstalled_at", sa.DateTime(), nullable=True))
    op.add_column("device_agents", sa.Column("service_state", sa.String(24), nullable=True))
    op.add_column("device_agents", sa.Column("service_last_seen_at", sa.DateTime(), nullable=True))
    op.add_column("device_agents", sa.Column("completion_hash", sa.String(64), nullable=True))
    op.add_column("device_agents", sa.Column("completion_expires_at", sa.DateTime(), nullable=True))
    # A prior heartbeat proves a worker was installed; revocation alone never
    # proves that files were removed. No existing credential or inventory changes.
    op.execute(sa.text("UPDATE device_agents SET installation_state = 'installed' WHERE last_seen_at IS NOT NULL"))


def downgrade():
    with op.batch_alter_table("device_agents") as table:
        for column in ("completion_expires_at", "completion_hash", "service_last_seen_at", "service_state", "uninstalled_at", "installation_state"):
            table.drop_column(column)
