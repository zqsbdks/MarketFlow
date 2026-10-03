"""数据库兜底：总部账号不归店，其他员工必须明确归店。"""

from alembic import op

revision = "20261002_0028"
down_revision = "20261002_0027"
branch_labels = depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_employee_store_matches_role",
        "employee",
        "(role = '总部' AND store_id IS NULL AND department_id IS NULL) "
        "OR (role <> '总部' AND store_id IS NOT NULL)",
    )


def downgrade():
    op.drop_constraint("ck_employee_store_matches_role", "employee", type_="check")
