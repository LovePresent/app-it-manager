"""Preserve a separate IP monitoring baseline and deduplicate change alerts."""
from alembic import op
import sqlalchemy as sa

revision = "20261025_agent_network"
down_revision = "20261025_unlimited_enroll"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("device_agents", sa.Column("network_monitor", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("device_agents") as batch:
        batch.drop_column("network_monitor")
