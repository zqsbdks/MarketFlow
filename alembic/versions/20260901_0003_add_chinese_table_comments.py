"""add Chinese comments to business tables

Revision ID: 20260901_0003
Revises: 20260901_0002
Create Date: 2026-09-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260901_0003"
down_revision: str | Sequence[str] | None = "20260901_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_COMMENTS = {
    "department": "部门表",
    "employee": "员工表",
    "category": "商品分类表",
    "product": "商品表",
    "sale": "销售单表",
    "sale_item": "销售明细表",
}


def upgrade() -> None:
    """为六张业务表添加中文说明。"""

    for table_name, comment in TABLE_COMMENTS.items():
        op.create_table_comment(table_name, comment, existing_comment=None)


def downgrade() -> None:
    """移除本迁移添加的中文表说明。"""

    for table_name, comment in TABLE_COMMENTS.items():
        op.drop_table_comment(table_name, existing_comment=comment)
