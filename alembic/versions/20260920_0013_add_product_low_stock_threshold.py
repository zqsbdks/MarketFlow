"""add product low stock threshold

Revision ID: 20260920_0013
Revises: 20260920_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0013"
down_revision: str | Sequence[str] | None = "20260920_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为商品增加可选的低库存预警阈值。"""

    op.add_column(
        "product",
        sa.Column(
            "low_stock_threshold",
            sa.Integer(),
            nullable=True,
            comment="低库存预警阈值",
        ),
    )
    op.create_check_constraint(
        "ck_product_low_stock_threshold_non_negative",
        "product",
        "low_stock_threshold IS NULL OR low_stock_threshold >= 0",
    )


def downgrade() -> None:
    """删除商品低库存预警阈值。"""

    op.drop_constraint(
        "ck_product_low_stock_threshold_non_negative",
        "product",
        type_="check",
    )
    op.drop_column("product", "low_stock_threshold")
