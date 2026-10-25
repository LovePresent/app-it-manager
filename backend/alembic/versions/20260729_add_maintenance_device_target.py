"""add maintenance device target

Revision ID: 20260729_maintenance_devices
Revises: 20260728_license_service_company
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_maintenance_devices"
down_revision = "20260728_license_service_company"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.alter_column(
            "asset_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(sa.Column("device_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_maintenance_records_device_id",
            ["device_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_maintenance_records_device_id_devices",
            "devices",
            ["device_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_maintenance_records_single_target",
            "(asset_id IS NOT NULL AND device_id IS NULL) OR "
            "(asset_id IS NULL AND device_id IS NOT NULL)",
        )


def downgrade():
    connection = op.get_bind()
    device_records = connection.execute(
        sa.text("SELECT COUNT(*) FROM maintenance_records WHERE device_id IS NOT NULL")
    ).scalar_one()
    if device_records:
        raise RuntimeError("디바이스 유지보수 기록이 있어 안전하게 다운그레이드할 수 없습니다.")

    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.drop_constraint("ck_maintenance_records_single_target", type_="check")
        batch_op.drop_constraint("fk_maintenance_records_device_id_devices", type_="foreignkey")
