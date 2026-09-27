"""remove discount stock thresholds

Revision ID: 20260927_0016
Revises: 20260921_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0016"
down_revision: str | Sequence[str] | None = "20260921_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# region 删除折扣库存阈值
def upgrade() -> None:
    """删除折扣规则不再使用的开始和停止库存阈值。"""

    # 必须先删除引用字段的检查约束，之后才能安全删除两个字段。
    op.drop_constraint(
        "ck_discount_rule_stock_range",
        "discount_rule",
        type_="check",
    )
    op.drop_constraint(
        "ck_discount_rule_end_stock_non_negative",
        "discount_rule",
        type_="check",
    )
    op.drop_constraint(
        "ck_discount_rule_start_stock_non_negative",
        "discount_rule",
        type_="check",
    )
    op.drop_column("discount_rule", "end_stock_threshold")
    op.drop_column("discount_rule", "start_stock_threshold")


# endregion


# region 恢复折扣库存阈值
def downgrade() -> None:
    """回退迁移时恢复两个可选库存阈值及其检查约束。"""

    op.add_column(
        "discount_rule",
        sa.Column(
            "start_stock_threshold",
            sa.Integer(),
            nullable=True,
            comment="可售库存小于等于该值时开始打折",
        ),
    )
    op.add_column(
        "discount_rule",
        sa.Column(
            "end_stock_threshold",
            sa.Integer(),
            nullable=True,
            comment="可售库存小于等于该值时停止打折",
        ),
    )
    op.create_check_constraint(
        "ck_discount_rule_start_stock_non_negative",
        "discount_rule",
        "start_stock_threshold IS NULL OR start_stock_threshold >= 0",
    )
    op.create_check_constraint(
        "ck_discount_rule_end_stock_non_negative",
        "discount_rule",
        "end_stock_threshold IS NULL OR end_stock_threshold >= 0",
    )
    op.create_check_constraint(
        "ck_discount_rule_stock_range",
        "discount_rule",
        "start_stock_threshold IS NULL OR end_stock_threshold IS NULL "
        "OR end_stock_threshold < start_stock_threshold",
    )


# endregion
