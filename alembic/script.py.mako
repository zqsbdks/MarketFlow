"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
${imports if imports else ""}

# Alembic 使用以下标识构建迁移版本链；生成后不要随意修改 revision。
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """按当前版本定义升级数据库结构。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """撤销 upgrade 中的结构变化。"""
    ${downgrades if downgrades else "pass"}
