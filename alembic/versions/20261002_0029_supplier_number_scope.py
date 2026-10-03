"""供应商编号允许不同门店分别从 SUP00001 起使用。"""

from alembic import op

revision = "20261002_0029"
down_revision = "20261002_0028"
branch_labels = depends_on = None


def upgrade():
    op.drop_index("uq_supplier_supplier_no", table_name="supplier")
    op.create_unique_constraint("uq_supplier_supplier_no", "supplier", ["store_id", "supplier_no"])


def downgrade():
    raise RuntimeError("跨店可能已有重复供应商编号，不能无损恢复全局唯一约束")
