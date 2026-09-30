"""add sale discount snapshots

Revision ID: 20260927_0018
Revises: 20260927_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0018"
down_revision: str | Sequence[str] | None = "20260927_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# region 增加销售折扣汇总和快照字段
def upgrade() -> None:
    """为销售单和销售明细增加折前金额、优惠金额及折扣规则快照。"""

    # 销售主表先使用默认值增加字段，再用已有实收金额补齐历史数据。
    op.add_column(
        "sale",
        sa.Column(
            "original_total_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
            comment="折扣前商品原价总金额",
        ),
    )
    op.add_column(
        "sale",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
            comment="整张销售单优惠总金额",
        ),
    )
    op.execute(
        sa.text("UPDATE sale SET original_total_amount = total_amount, discount_amount = 0.00")
    )

    # 历史销售没有折扣，因此原单价等于成交价，优惠金额为0。
    op.add_column(
        "sale_item",
        sa.Column(
            "original_unit_price",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0.00",
            comment="成交前商品原销售单价",
        ),
    )
    op.add_column(
        "sale_item",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
            comment="本条销售明细优惠总金额",
        ),
    )
    op.add_column(
        "sale_item",
        sa.Column(
            "discount_rule_id",
            sa.BigInteger(),
            nullable=True,
            comment="成交时使用的折扣规则ID",
        ),
    )
    op.add_column(
        "sale_item",
        sa.Column(
            "discount_rule_name_snapshot",
            sa.String(100),
            nullable=True,
            comment="成交时折扣规则名称快照",
        ),
    )
    op.add_column(
        "sale_item",
        sa.Column(
            "discount_type_snapshot",
            sa.String(20),
            nullable=True,
            comment="成交时折扣计算方式快照",
        ),
    )
    op.add_column(
        "sale_item",
        sa.Column(
            "discount_value_snapshot",
            sa.Numeric(12, 4),
            nullable=True,
            comment="成交时折扣数值快照",
        ),
    )
    op.execute(
        sa.text("UPDATE sale_item SET original_unit_price = unit_price, discount_amount = 0.00")
    )
    op.create_index(
        "ix_sale_item_discount_rule_id",
        "sale_item",
        ["discount_rule_id"],
    )
    op.create_foreign_key(
        "fk_sale_item_discount_rule_id",
        "sale_item",
        "discount_rule",
        ["discount_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 数据补齐后再添加金额一致性约束，保证以后写入的数据可以互相核对。
    op.create_check_constraint(
        "ck_sale_original_total_amount_non_negative",
        "sale",
        "original_total_amount >= 0",
    )
    op.create_check_constraint(
        "ck_sale_discount_amount_non_negative",
        "sale",
        "discount_amount >= 0",
    )
    op.create_check_constraint(
        "ck_sale_discount_amount_matches_totals",
        "sale",
        "original_total_amount = total_amount + discount_amount",
    )
    op.create_check_constraint(
        "ck_sale_item_original_unit_price_non_negative",
        "sale_item",
        "original_unit_price >= 0",
    )
    op.create_check_constraint(
        "ck_sale_item_discount_does_not_raise_price",
        "sale_item",
        "original_unit_price >= unit_price",
    )
    op.create_check_constraint(
        "ck_sale_item_discount_amount_non_negative",
        "sale_item",
        "discount_amount >= 0",
    )
    op.create_check_constraint(
        "ck_sale_item_discount_amount_matches",
        "sale_item",
        "discount_amount = (original_unit_price - unit_price) * quantity",
    )


# endregion


# region 删除销售折扣汇总和快照字段
def downgrade() -> None:
    """回退销售折扣字段、约束、索引和外键。"""

    op.drop_constraint("ck_sale_item_discount_amount_matches", "sale_item", type_="check")
    op.drop_constraint(
        "ck_sale_item_discount_amount_non_negative",
        "sale_item",
        type_="check",
    )
    op.drop_constraint(
        "ck_sale_item_discount_does_not_raise_price",
        "sale_item",
        type_="check",
    )
    op.drop_constraint(
        "ck_sale_item_original_unit_price_non_negative",
        "sale_item",
        type_="check",
    )
    op.drop_constraint("ck_sale_discount_amount_matches_totals", "sale", type_="check")
    op.drop_constraint("ck_sale_discount_amount_non_negative", "sale", type_="check")
    op.drop_constraint(
        "ck_sale_original_total_amount_non_negative",
        "sale",
        type_="check",
    )
    op.drop_constraint("fk_sale_item_discount_rule_id", "sale_item", type_="foreignkey")
    op.drop_index("ix_sale_item_discount_rule_id", table_name="sale_item")
    op.drop_column("sale_item", "discount_value_snapshot")
    op.drop_column("sale_item", "discount_type_snapshot")
    op.drop_column("sale_item", "discount_rule_name_snapshot")
    op.drop_column("sale_item", "discount_rule_id")
    op.drop_column("sale_item", "discount_amount")
    op.drop_column("sale_item", "original_unit_price")
    op.drop_column("sale", "discount_amount")
    op.drop_column("sale", "original_total_amount")


# endregion
