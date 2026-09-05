"""验证第一版 MarketFlow ORM 元数据和数据库约束。"""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Numeric
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app.models import (
    Base,
    Employee,
    EmployeeDetail,
    EmployeeGender,
    EmployeeRole,
    EmploymentStatus,
    Product,
    ProductStatus,
    Sale,
    SaleSource,
)

EXPECTED_COLUMNS = {
    "department": {"id", "code", "name", "is_active", "created_at", "updated_at"},
    "employee": {
        "id",
        "employee_no",
        "name",
        "password_hash",
        "role",
        "department_id",
        "is_active",
        "must_change_password",
        "last_login_at",
        "created_at",
        "updated_at",
    },
    "employee_detail": {
        "employee_id",
        "gender",
        "birth_date",
        "hire_date",
        "phone",
        "address",
        "employment_status",
        "separation_date",
        "separation_reason",
        "created_at",
        "updated_at",
    },
    "category": {"id", "department_id", "name", "is_active", "created_at", "updated_at"},
    "product": {
        "id",
        "product_no",
        "name",
        "department_id",
        "category_id",
        "purchase_price",
        "sale_price",
        "stock_quantity",
        "status",
        "created_at",
        "updated_at",
    },
    "sale": {
        "id",
        "sale_no",
        "sold_at",
        "total_amount",
        "total_cost",
        "gross_profit",
        "source",
        "created_at",
    },
    "sale_item": {
        "id",
        "sale_id",
        "product_id",
        "product_no_snapshot",
        "product_name_snapshot",
        "department_id",
        "quantity",
        "unit_price",
        "unit_cost",
        "subtotal",
        "cost_subtotal",
    },
}

EXPECTED_TABLE_COMMENTS = {
    "department": "部门表",
    "employee": "员工表",
    "employee_detail": "员工详情表",
    "category": "商品分类表",
    "product": "商品表",
    "sale": "销售单表",
    "sale_item": "销售明细表",
}


def test_employee_detail_is_the_seventh_business_table() -> None:
    """员工详情作为第七张业务表，并继续排除独立库存表。"""

    assert set(Base.metadata.tables) == set(EXPECTED_COLUMNS)
    assert "inventory" not in Base.metadata.tables


def test_model_columns_match_first_version_design() -> None:
    """每张表的字段集合与已确认的第一版设计一致。"""

    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == expected_columns


def test_every_business_column_has_chinese_comment() -> None:
    """数据库工具可以在全部业务字段下显示中文说明。"""

    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            assert column.comment


def test_every_business_table_has_chinese_comment() -> None:
    """全部业务表都带有用于数据库工具展示的中文说明。"""

    for table_name, expected_comment in EXPECTED_TABLE_COMMENTS.items():
        assert Base.metadata.tables[table_name].comment == expected_comment


def test_inventory_is_stored_on_product_with_non_negative_constraint() -> None:
    """库存数量位于商品表，并由数据库约束禁止负数。"""

    assert Product.__table__.c.stock_quantity.server_default.arg.text == "0"
    check_names = {
        constraint.name
        for constraint in Product.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_product_stock_quantity_non_negative" in check_names


def test_product_category_must_belong_to_same_department() -> None:
    """复合外键禁止商品引用其他部门的分类。"""

    foreign_keys = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in Product.__table__.foreign_key_constraints
    }
    assert foreign_keys["fk_product_category_department"] == (
        "category_id",
        "department_id",
    )


def test_money_columns_use_exact_decimal_types() -> None:
    """价格、金额和成本列必须使用指定精度的 DECIMAL。"""

    expected_precision = {
        ("product", "purchase_price"): (10, 2),
        ("product", "sale_price"): (10, 2),
        ("sale", "total_amount"): (12, 2),
        ("sale", "total_cost"): (12, 2),
        ("sale", "gross_profit"): (12, 2),
        ("sale_item", "unit_price"): (10, 2),
        ("sale_item", "unit_cost"): (10, 2),
        ("sale_item", "subtotal"): (12, 2),
        ("sale_item", "cost_subtotal"): (12, 2),
    }

    for (table_name, column_name), (precision, scale) in expected_precision.items():
        column_type = Base.metadata.tables[table_name].c[column_name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale) == (precision, scale)


def test_enum_values_match_confirmed_business_values() -> None:
    """员工角色、商品状态和销售来源只接受第一版值。"""

    assert Employee.__table__.c.role.type.enums == [item.value for item in EmployeeRole]
    assert Product.__table__.c.status.type.enums == [item.value for item in ProductStatus]
    assert Sale.__table__.c.source.type.enums == [item.value for item in SaleSource]
    assert EmployeeDetail.__table__.c.gender.type.enums == [item.value for item in EmployeeGender]
    assert EmployeeDetail.__table__.c.employment_status.type.enums == [
        item.value for item in EmploymentStatus
    ]

    expected_constraint_names = {
        "employee": "employee_role",
        "product": "product_status",
        "sale": "sale_source",
        "employee_detail": "employee_detail_employment_status",
    }
    for table_name, constraint_name in expected_constraint_names.items():
        check_names = {
            constraint.name
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert constraint_name in check_names


def test_all_tables_explicitly_use_utf8mb4() -> None:
    """所有表都显式声明 MySQL utf8mb4 字符集。"""

    for table in Base.metadata.sorted_tables:
        assert table.dialect_options["mysql"]["charset"] == "utf8mb4"
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "CHARSET=utf8mb4" in ddl


def test_mutable_master_tables_update_timestamp_in_mysql() -> None:
    """主数据表由 MySQL 自动维护 updated_at，避免绕过 ORM 时留下旧时间。"""

    for table_name in ("department", "employee", "employee_detail", "category", "product"):
        ddl = str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=mysql.dialect()))
        assert "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP" in ddl


def test_all_relationship_mappers_can_be_configured() -> None:
    """跨模块关系没有循环导入或 back_populates 配置错误。"""

    configure_mappers()


def test_latest_alembic_revision_is_the_only_head() -> None:
    """员工角色中文化迁移是当前唯一的 Alembic 版本头。"""

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260905_0005"]
