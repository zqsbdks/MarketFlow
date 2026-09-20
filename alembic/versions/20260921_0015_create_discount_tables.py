"""create discount rule and scope tables

Revision ID: 20260921_0015
Revises: 20260920_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0015"
down_revision: str | Sequence[str] | None = "20260920_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# region 创建折扣数据表
def upgrade() -> None:
    """依次创建实际折扣规则和规则适用范围表。"""

    # 折扣规则会被长期保留；过期后只改变计算状态，不会被自动删除。
    op.create_table(
        "discount_rule",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="折扣规则主键",
        ),
        sa.Column("name", sa.String(length=100), nullable=False, comment="折扣规则名称"),
        sa.Column(
            "discount_type",
            sa.String(length=20),
            nullable=False,
            comment="折扣计算方式",
        ),
        sa.Column(
            "discount_value",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            comment="折扣比例、立减金额或固定价格",
        ),
        sa.Column(
            "schedule_type",
            sa.String(length=20),
            nullable=False,
            comment="折扣执行周期",
        ),
        sa.Column("starts_at", sa.DateTime(), nullable=True, comment="单次活动开始时间"),
        sa.Column("ends_at", sa.DateTime(), nullable=True, comment="单次活动结束时间"),
        sa.Column("daily_start_time", sa.Time(), nullable=True, comment="每日循环开始时间"),
        sa.Column("daily_end_time", sa.Time(), nullable=True, comment="每日循环结束时间"),
        sa.Column(
            "weekdays",
            sa.JSON(),
            nullable=True,
            comment="每周执行日列表；1至7表示周一至周日",
        ),
        sa.Column(
            "start_stock_threshold",
            sa.Integer(),
            nullable=True,
            comment="可售库存小于等于该值时开始打折",
        ),
        sa.Column(
            "end_stock_threshold",
            sa.Integer(),
            nullable=True,
            comment="可售库存小于等于该值时停止打折",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
            comment="折扣规则是否启用",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False, comment="创建员工ID"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
            comment="更新时间",
        ),
        sa.CheckConstraint(
            "discount_type IN ('percentage', 'amount_off', 'fixed_price')",
            name="discount_rule_type",
        ),
        sa.CheckConstraint(
            "schedule_type IN ('once', 'daily', 'weekly')",
            name="discount_rule_schedule_type",
        ),
        sa.CheckConstraint(
            "discount_value > 0 AND (discount_type <> 'percentage' OR discount_value < 1)",
            name="ck_discount_rule_value",
        ),
        sa.CheckConstraint(
            "(schedule_type = 'once' AND starts_at IS NOT NULL AND ends_at IS NOT NULL) OR "
            "(schedule_type IN ('daily', 'weekly') AND daily_start_time IS NOT NULL "
            "AND daily_end_time IS NOT NULL)",
            name="ck_discount_rule_schedule_fields",
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR starts_at < ends_at",
            name="ck_discount_rule_datetime_range",
        ),
        sa.CheckConstraint(
            "daily_start_time IS NULL OR daily_end_time IS NULL "
            "OR daily_start_time < daily_end_time",
            name="ck_discount_rule_daily_time_range",
        ),
        sa.CheckConstraint(
            "start_stock_threshold IS NULL OR start_stock_threshold >= 0",
            name="ck_discount_rule_start_stock_non_negative",
        ),
        sa.CheckConstraint(
            "end_stock_threshold IS NULL OR end_stock_threshold >= 0",
            name="ck_discount_rule_end_stock_non_negative",
        ),
        sa.CheckConstraint(
            "start_stock_threshold IS NULL OR end_stock_threshold IS NULL "
            "OR end_stock_threshold < start_stock_threshold",
            name="ck_discount_rule_stock_range",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["employee.id"],
            name="fk_discount_rule_created_by_employee",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_discount_rule_name"),
        comment="折扣规则表",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_discount_rule_starts_at", "discount_rule", ["starts_at"])
    op.create_index("ix_discount_rule_ends_at", "discount_rule", ["ends_at"])
    op.create_index("ix_discount_rule_created_by", "discount_rule", ["created_by"])
    op.create_index(
        "ix_discount_rule_active_schedule",
        "discount_rule",
        ["is_active", "schedule_type"],
    )

    # 一行范围只允许指向一个商品、一个分类或一个部门。
    op.create_table(
        "discount_rule_scope",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="折扣规则范围主键",
        ),
        sa.Column("discount_rule_id", sa.BigInteger(), nullable=False, comment="折扣规则ID"),
        sa.Column("scope_type", sa.String(length=20), nullable=False, comment="适用范围类型"),
        sa.Column("product_id", sa.BigInteger(), nullable=True, comment="适用商品ID"),
        sa.Column("category_id", sa.BigInteger(), nullable=True, comment="适用商品分类ID"),
        sa.Column("department_id", sa.BigInteger(), nullable=True, comment="适用部门ID"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="创建时间",
        ),
        sa.CheckConstraint(
            "scope_type IN ('product', 'category', 'department')",
            name="discount_rule_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'product' AND product_id IS NOT NULL "
            "AND category_id IS NULL AND department_id IS NULL) OR "
            "(scope_type = 'category' AND product_id IS NULL "
            "AND category_id IS NOT NULL AND department_id IS NULL) OR "
            "(scope_type = 'department' AND product_id IS NULL "
            "AND category_id IS NULL AND department_id IS NOT NULL)",
            name="ck_discount_rule_scope_single_target",
        ),
        sa.ForeignKeyConstraint(
            ["discount_rule_id"],
            ["discount_rule.id"],
            name="fk_discount_rule_scope_rule",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.id"],
            name="fk_discount_rule_scope_product",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["category.id"],
            name="fk_discount_rule_scope_category",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_discount_rule_scope_department",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "discount_rule_id",
            "product_id",
            name="uq_discount_rule_scope_product",
        ),
        sa.UniqueConstraint(
            "discount_rule_id",
            "category_id",
            name="uq_discount_rule_scope_category",
        ),
        sa.UniqueConstraint(
            "discount_rule_id",
            "department_id",
            name="uq_discount_rule_scope_department",
        ),
        comment="折扣规则适用范围表",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_discount_rule_scope_discount_rule_id",
        "discount_rule_scope",
        ["discount_rule_id"],
    )
    op.create_index("ix_discount_rule_scope_scope_type", "discount_rule_scope", ["scope_type"])
    op.create_index("ix_discount_rule_scope_product_id", "discount_rule_scope", ["product_id"])
    op.create_index("ix_discount_rule_scope_category_id", "discount_rule_scope", ["category_id"])
    op.create_index(
        "ix_discount_rule_scope_department_id",
        "discount_rule_scope",
        ["department_id"],
    )


# endregion


# region 删除折扣数据表
def downgrade() -> None:
    """按外键依赖的反向顺序删除两张折扣表。"""

    op.drop_table("discount_rule_scope")
    op.drop_table("discount_rule")


# endregion
