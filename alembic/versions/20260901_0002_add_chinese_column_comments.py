"""add Chinese comments to business columns

Revision ID: 20260901_0002
Revises: 20260901_0001
Create Date: 2026-09-01

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0002"
down_revision: str | Sequence[str] | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NO_DEFAULT = object()


def _column_specs() -> list[tuple[str, str, sa.types.TypeEngine[Any], bool, str, object, bool]]:
    """返回表名、字段、类型、可空性、注释、默认值和自增信息。"""

    created_default = sa.text("CURRENT_TIMESTAMP")
    updated_default = sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    return [
        ("department", "id", sa.BigInteger(), False, "部门主键", _NO_DEFAULT, True),
        ("department", "code", sa.String(20), False, "部门代码", _NO_DEFAULT, False),
        ("department", "name", sa.String(50), False, "部门名称", _NO_DEFAULT, False),
        ("department", "is_active", sa.Boolean(), False, "是否启用", sa.text("1"), False),
        ("department", "created_at", sa.DateTime(), False, "创建时间", created_default, False),
        ("department", "updated_at", sa.DateTime(), False, "更新时间", updated_default, False),
        ("employee", "id", sa.BigInteger(), False, "员工主键", _NO_DEFAULT, True),
        ("employee", "employee_no", sa.String(20), False, "员工编号", _NO_DEFAULT, False),
        ("employee", "name", sa.String(50), False, "员工姓名", _NO_DEFAULT, False),
        ("employee", "password_hash", sa.String(255), False, "密码哈希", _NO_DEFAULT, False),
        ("employee", "role", sa.String(30), False, "员工类型", _NO_DEFAULT, False),
        ("employee", "department_id", sa.BigInteger(), True, "所属部门", _NO_DEFAULT, False),
        ("employee", "is_active", sa.Boolean(), False, "账号是否启用", sa.text("1"), False),
        (
            "employee",
            "must_change_password",
            sa.Boolean(),
            False,
            "是否必须修改密码",
            sa.text("1"),
            False,
        ),
        ("employee", "last_login_at", sa.DateTime(), True, "最后登录时间", _NO_DEFAULT, False),
        ("employee", "created_at", sa.DateTime(), False, "创建时间", created_default, False),
        ("employee", "updated_at", sa.DateTime(), False, "更新时间", updated_default, False),
        ("category", "id", sa.BigInteger(), False, "分类主键", _NO_DEFAULT, True),
        ("category", "department_id", sa.BigInteger(), False, "所属部门", _NO_DEFAULT, False),
        ("category", "name", sa.String(50), False, "分类名称", _NO_DEFAULT, False),
        ("category", "is_active", sa.Boolean(), False, "是否启用", sa.text("1"), False),
        ("category", "created_at", sa.DateTime(), False, "创建时间", created_default, False),
        ("category", "updated_at", sa.DateTime(), False, "更新时间", updated_default, False),
        ("product", "id", sa.BigInteger(), False, "商品主键", _NO_DEFAULT, True),
        ("product", "product_no", sa.String(20), False, "商品编号", _NO_DEFAULT, False),
        ("product", "name", sa.String(100), False, "商品名称", _NO_DEFAULT, False),
        ("product", "department_id", sa.BigInteger(), False, "所属部门", _NO_DEFAULT, False),
        ("product", "category_id", sa.BigInteger(), False, "所属分类", _NO_DEFAULT, False),
        ("product", "purchase_price", sa.Numeric(10, 2), False, "进货价", _NO_DEFAULT, False),
        ("product", "sale_price", sa.Numeric(10, 2), False, "销售价", _NO_DEFAULT, False),
        ("product", "stock_quantity", sa.Integer(), False, "当前库存数量", sa.text("0"), False),
        ("product", "status", sa.String(20), False, "商品销售状态", sa.text("'on_sale'"), False),
        ("product", "created_at", sa.DateTime(), False, "创建时间", created_default, False),
        ("product", "updated_at", sa.DateTime(), False, "更新时间", updated_default, False),
        ("sale", "id", sa.BigInteger(), False, "销售单主键", _NO_DEFAULT, True),
        ("sale", "sale_no", sa.String(30), False, "销售单号", _NO_DEFAULT, False),
        ("sale", "sold_at", sa.DateTime(), False, "销售发生时间", _NO_DEFAULT, False),
        ("sale", "total_amount", sa.Numeric(12, 2), False, "销售总金额", _NO_DEFAULT, False),
        ("sale", "total_cost", sa.Numeric(12, 2), False, "商品总成本", _NO_DEFAULT, False),
        ("sale", "gross_profit", sa.Numeric(12, 2), False, "毛利润", _NO_DEFAULT, False),
        ("sale", "source", sa.String(30), False, "数据来源", sa.text("'demo_seed'"), False),
        ("sale", "created_at", sa.DateTime(), False, "创建时间", created_default, False),
        ("sale_item", "id", sa.BigInteger(), False, "销售明细主键", _NO_DEFAULT, True),
        ("sale_item", "sale_id", sa.BigInteger(), False, "所属销售单", _NO_DEFAULT, False),
        ("sale_item", "product_id", sa.BigInteger(), False, "商品主键", _NO_DEFAULT, False),
        (
            "sale_item",
            "product_no_snapshot",
            sa.String(20),
            False,
            "成交时商品编号",
            _NO_DEFAULT,
            False,
        ),
        (
            "sale_item",
            "product_name_snapshot",
            sa.String(100),
            False,
            "成交时商品名称",
            _NO_DEFAULT,
            False,
        ),
        (
            "sale_item",
            "department_id",
            sa.BigInteger(),
            False,
            "成交时所属部门",
            _NO_DEFAULT,
            False,
        ),
        ("sale_item", "quantity", sa.Integer(), False, "销售数量", _NO_DEFAULT, False),
        ("sale_item", "unit_price", sa.Numeric(10, 2), False, "成交单价", _NO_DEFAULT, False),
        ("sale_item", "unit_cost", sa.Numeric(10, 2), False, "成交时成本价", _NO_DEFAULT, False),
        ("sale_item", "subtotal", sa.Numeric(12, 2), False, "商品销售小计", _NO_DEFAULT, False),
        (
            "sale_item",
            "cost_subtotal",
            sa.Numeric(12, 2),
            False,
            "商品成本小计",
            _NO_DEFAULT,
            False,
        ),
    ]


def _set_comments(enabled: bool) -> None:
    """添加或移除所有业务字段的中文注释。"""

    for table, column, type_, nullable, comment, default, autoincrement in _column_specs():
        options: dict[str, object] = {
            "existing_type": type_,
            "existing_nullable": nullable,
            "existing_autoincrement": autoincrement,
            "comment": comment if enabled else None,
            "existing_comment": None if enabled else comment,
        }
        if default is not _NO_DEFAULT:
            options["existing_server_default"] = default
        op.alter_column(table, column, **options)


def upgrade() -> None:
    """为所有业务字段添加中文说明。"""

    _set_comments(enabled=True)


def downgrade() -> None:
    """移除本迁移添加的中文说明。"""

    _set_comments(enabled=False)
