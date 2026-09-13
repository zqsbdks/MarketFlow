"""add supplier product category

Revision ID: 20260913_0007
Revises: 3878bf50f212
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0007"
down_revision: str | Sequence[str] | None = "3878bf50f212"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """给供应商商品目录增加商品分类。"""
    op.add_column(
        "supplier_product",
        sa.Column("category_id", sa.BigInteger(), nullable=True, comment="商品分类ID"),
    )
    op.create_index(
        op.f("ix_supplier_product_category_id"),
        "supplier_product",
        ["category_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_supplier_product_category_id",
        "supplier_product",
        "category",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """移除供应商商品目录的商品分类。"""
    op.drop_constraint("fk_supplier_product_category_id", "supplier_product", type_="foreignkey")
    op.drop_index(op.f("ix_supplier_product_category_id"), table_name="supplier_product")
    op.drop_column("supplier_product", "category_id")
