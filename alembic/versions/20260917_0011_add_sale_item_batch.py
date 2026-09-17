"""add inventory batch source to sale items

Revision ID: 20260917_0011
Revises: 20260917_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0011"
down_revision: str | Sequence[str] | None = "20260917_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为销售明细增加实际扣减批次，并允许收银台来源。"""

    op.add_column(
        "sale_item",
        sa.Column(
            "inventory_batch_id",
            sa.BigInteger(),
            nullable=True,
            comment="实际扣减的库存批次ID",
        ),
    )
    op.create_index(
        op.f("ix_sale_item_inventory_batch_id"),
        "sale_item",
        ["inventory_batch_id"],
    )
    op.create_foreign_key(
        "fk_sale_item_inventory_batch_id",
        "sale_item",
        "inventory_batch",
        ["inventory_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("sale_source", "sale", type_="check")
    op.create_check_constraint("sale_source", "sale", "source IN ('demo_seed', 'pos')")


def downgrade() -> None:
    """删除销售明细批次来源，并恢复旧的销售来源范围。"""

    op.drop_constraint("sale_source", "sale", type_="check")
    op.execute(sa.text("UPDATE sale SET source = 'demo_seed' WHERE source = 'pos'"))
    op.create_check_constraint("sale_source", "sale", "source IN ('demo_seed')")
    op.drop_constraint("fk_sale_item_inventory_batch_id", "sale_item", type_="foreignkey")
    op.drop_index(op.f("ix_sale_item_inventory_batch_id"), table_name="sale_item")
    op.drop_column("sale_item", "inventory_batch_id")
