"""add required department to discount rule

Revision ID: 20260927_0017
Revises: 20260927_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0017"
down_revision: str | Sequence[str] | None = "20260927_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# region 增加折扣规则所属部门
def upgrade() -> None:
    """增加必填部门字段，并为已有折扣规则补齐部门。"""

    # 先以可空字段加入，避免已有折扣规则导致添加字段立即失败。
    op.add_column(
        "discount_rule",
        sa.Column(
            "department_id",
            sa.BigInteger(),
            nullable=True,
            comment="折扣规则所属部门ID",
        ),
    )

    # 已有规则优先使用其第一个关联商品的部门，其次使用创建员工的部门。
    # 店长没有所属部门且规则尚未添加商品时，使用现有部门中的最小ID完成历史数据迁移。
    op.execute(
        sa.text(
            """
            UPDATE discount_rule AS rule_row
            SET department_id = COALESCE(
                (
                    SELECT product.department_id
                    FROM discount_rule_scope AS scope
                    INNER JOIN product ON product.id = scope.product_id
                    WHERE scope.discount_rule_id = rule_row.id
                      AND scope.scope_type = 'product'
                    ORDER BY scope.id ASC
                    LIMIT 1
                ),
                (
                    SELECT employee.department_id
                    FROM employee
                    WHERE employee.id = rule_row.created_by
                ),
                (
                    SELECT MIN(department.id)
                    FROM department
                )
            )
            WHERE rule_row.department_id IS NULL
            """
        )
    )

    # 历史数据补齐后，正式改成必填字段并建立索引和外键。
    op.alter_column(
        "discount_rule",
        "department_id",
        existing_type=sa.BigInteger(),
        nullable=False,
        existing_comment="折扣规则所属部门ID",
    )
    op.create_index(
        "ix_discount_rule_department_id",
        "discount_rule",
        ["department_id"],
    )
    op.create_foreign_key(
        "fk_discount_rule_department_id",
        "discount_rule",
        "department",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )


# endregion


# region 删除折扣规则所属部门
def downgrade() -> None:
    """回退时删除折扣规则所属部门外键、索引和字段。"""

    op.drop_constraint(
        "fk_discount_rule_department_id",
        "discount_rule",
        type_="foreignkey",
    )
    op.drop_index("ix_discount_rule_department_id", table_name="discount_rule")
    op.drop_column("discount_rule", "department_id")


# endregion
