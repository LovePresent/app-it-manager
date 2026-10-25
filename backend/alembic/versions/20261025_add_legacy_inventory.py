"""Add inventory tables absent from the last successful b856260 deployment.

Independent prerequisite branch; the guard runs it before the unchanged main
chain, whose first IP-history migration must remain unchanged. Existing exact
tables are validated and retained. No business records are inserted or deleted.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_legacy_inventory"
down_revision = None
branch_labels = ("legacy_inventory",)
depends_on = None


def tables():
    metadata = sa.MetaData()
    def col(name, kind=sa.String, **kw):
        return sa.Column(name, kind(), **kw)
    def stamps():
        return [col("created_at", sa.DateTime, server_default=sa.func.now()),
                col("updated_at", sa.DateTime, server_default=sa.func.now())]
    device = sa.Table("devices", metadata,
        col("id", sa.Integer, primary_key=True, index=True),
        col("user_name", index=True), col("employee_number", index=True),
        col("serial_number", nullable=False, unique=True, index=True),
        col("device_type", nullable=False, index=True),
        *[col(name) for name in ("cpu", "memory", "storage", "gpu", "os_version")],
        col("ip_address", index=True), col("mac_address", index=True),
        col("purchase_date", sa.Date), col("manufacture_date", sa.Date),
        *[col(name, index=True) for name in ("location", "department", "factory")],
        col("status", nullable=False, index=True), col("notes", sa.Text), *stamps())
    licenses = sa.Table("device_licenses", metadata,
        col("id", sa.Integer, primary_key=True, index=True),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id"), nullable=False, index=True),
        *[col(name, sa.Boolean, nullable=False) for name in ("hangul", "ms_office", "cad", "windows_security", "pc_manager", "dlp", "av", "edr")],
        *[col(name, sa.Date) for name in ("purchase_date", "manufacture_date", "renewal_date")],
        col("notes", sa.Text), *stamps(), sa.UniqueConstraint("device_id", name="uq_device_licenses_device_id"))
    settings = sa.Table("computer_settings", metadata,
        col("id", sa.Integer, primary_key=True, index=True),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id"), nullable=False, index=True),
        *[col(name, sa.Boolean, nullable=False) for name in ("smart_app_control", "reputation_based_protection", "exploit_protection", "core_isolation")],
        col("notes", sa.Text), *stamps(), sa.UniqueConstraint("device_id", name="uq_computer_settings_device_id"))
    history = sa.Table("device_usage_history", metadata,
        col("id", sa.Integer, primary_key=True, index=True),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id"), nullable=False, index=True),
        col("user_name", index=True), col("employee_number", index=True), col("serial_number", nullable=False, index=True),
        col("started_at", sa.DateTime, nullable=False, server_default=sa.func.now()), col("ended_at", sa.DateTime),
        col("change_reason", nullable=False, index=True), col("notes", sa.Text),
        col("created_at", sa.DateTime, server_default=sa.func.now()))
    ai = sa.Table("ai_usage_subscriptions", metadata,
        col("id", sa.Integer, primary_key=True, index=True), col("service_name", nullable=False, index=True),
        col("provider", index=True), col("model_name", index=True), col("plan_name"),
        *[col(name, index=True) for name in ("account_email", "owner_name", "employee_number", "department")],
        col("billing_cycle"), col("monthly_cost", sa.Float), col("token_limit", sa.Integer), col("used_tokens", sa.Integer),
        col("renewal_date", sa.Date), col("auto_renew", sa.Boolean, nullable=False),
        col("status", nullable=False, index=True), col("usage_purpose", sa.Text), col("notes", sa.Text), *stamps())
    return [device, licenses, settings, history, ai]


def validate_existing(bind, table):
    inspector = sa.inspect(bind)
    actual = inspector.get_columns(table.name)
    if [(column["name"], str(column["type"]), column["nullable"], bool(column.get("primary_key"))) for column in actual] != [
        (column.name, str(column.type.compile(dialect=bind.dialect)), column.nullable, column.primary_key) for column in table.columns
    ]:
        raise RuntimeError("Existing legacy inventory schema differs; migration stopped.")
    existing_indexes = sorted((item["name"], bool(item["unique"]), tuple(item["column_names"])) for item in inspector.get_indexes(table.name))
    expected_indexes = sorted((item.name, bool(item.unique), tuple(column.name for column in item.columns)) for item in table.indexes)
    existing_unique = sorted(tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name))
    expected_unique = sorted(tuple(column.name for column in item.columns) for item in table.constraints if isinstance(item, sa.UniqueConstraint))
    existing_fk = sorted((tuple(item["constrained_columns"]), item["referred_table"], tuple(item["referred_columns"])) for item in inspector.get_foreign_keys(table.name))
    expected_fk = sorted((tuple(element.parent.name for element in item.elements), item.referred_table.name,
                          tuple(element.column.name for element in item.elements)) for item in table.foreign_key_constraints)
    if existing_indexes != expected_indexes or existing_unique != expected_unique or existing_fk != expected_fk:
        raise RuntimeError("Existing legacy inventory constraints differ; migration stopped.")


def upgrade():
    bind = op.get_bind()
    for table in tables():
        if sa.inspect(bind).has_table(table.name):
            validate_existing(bind, table)
        else:
            table.create(bind)


def downgrade():
    raise RuntimeError("Automatic removal of inventory tables is prohibited; preserve the database and roll back application images only.")
