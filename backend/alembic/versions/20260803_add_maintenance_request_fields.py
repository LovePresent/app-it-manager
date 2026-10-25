"""add maintenance request department and requester

Revision ID: 20260803_maintenance_requester
Revises: 20260729_maint_unregistered
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_maintenance_requester"
down_revision = "20260729_maint_unregistered"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("request_department", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("requester", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.drop_column("requester")
        batch_op.drop_column("request_department")

