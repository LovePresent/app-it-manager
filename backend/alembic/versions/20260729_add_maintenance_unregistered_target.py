"""add unregistered maintenance target

Revision ID: 20260729_maint_unregistered
Revises: 20260729_maintenance_devices
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_maint_unregistered"
down_revision = "20260729_maintenance_devices"
branch_labels = None
depends_on = None


_OLD_TARGET_CHECK = (
    "(asset_id IS NOT NULL AND device_id IS NULL) OR "
    "(asset_id IS NULL AND device_id IS NOT NULL)"
)
_NEW_TARGET_CHECK = (
    "(asset_id IS NOT NULL AND device_id IS NULL AND unregistered_target IS FALSE) OR "
    "(asset_id IS NULL AND device_id IS NOT NULL AND unregistered_target IS FALSE) OR "
    "(asset_id IS NULL AND device_id IS NULL AND unregistered_target IS TRUE)"
)


def upgrade():
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.drop_constraint("ck_maintenance_records_single_target", type_="check")
        batch_op.add_column(
            sa.Column(
                "unregistered_target",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_maintenance_records_single_target",
            _NEW_TARGET_CHECK,
        )


def downgrade():
    connection = op.get_bind()
    unregistered_records = connection.execute(
        sa.text("SELECT COUNT(*) FROM maintenance_records WHERE unregistered_target IS TRUE")
    ).scalar_one()
    if unregistered_records:
        raise RuntimeError("미등록 대상 유지보수 기록이 있어 안전하게 다운그레이드할 수 없습니다.")

    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.drop_constraint("ck_maintenance_records_single_target", type_="check")
        batch_op.drop_column("unregistered_target")
        batch_op.create_check_constraint(
            "ck_maintenance_records_single_target",
            _OLD_TARGET_CHECK,
        )
