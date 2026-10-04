"""自动补货数量与商品保底库存。"""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0031"
down_revision = "c453fbf6a0a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "supplier_product",
        sa.Column(
            "minimum_stock",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="自动补货保底库存",
        ),
    )
    op.add_column(
        "purchase_plan",
        sa.Column("automatic_quantities", sa.JSON(), nullable=True, comment="自动计算的订货数量"),
    )
    op.execute("UPDATE purchase_plan SET automatic_quantities = JSON_OBJECT()")
    op.alter_column(
        "purchase_plan", "automatic_quantities", existing_type=sa.JSON(), nullable=False
    )


def downgrade():
    op.drop_column("purchase_plan", "automatic_quantities")
    op.drop_column("supplier_product", "minimum_stock")
