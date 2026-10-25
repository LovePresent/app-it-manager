"""add maintenance received date

Revision ID: 20261008_maintenance_received
Revises: 20261007_project_history
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_maintenance_received"
down_revision = "20261007_project_history"
branch_labels = None
depends_on = None


def upgrade():
    # Historical receipt dates are unknown; keep existing records nullable.
    op.add_column("maintenance_records", sa.Column("received_date", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.drop_column("received_date")
