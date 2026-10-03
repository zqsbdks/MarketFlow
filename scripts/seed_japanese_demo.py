"""向空数据库写入约两个月的日语超市演示数据。

本脚本专门用于面试演示环境。它保留已有店长账号，只在其余业务表为空时执行，
从而避免误删或覆盖人工录入的数据。生成结果包含部门、分类、员工、供应商、商品、
进货、库存批次、折扣、销售和操作审计记录，并保持金额与库存之间的数据一致性。
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import TextIOWrapper
from pathlib import Path

# 直接执行 ``python scripts/seed_japanese_demo.py`` 时，Python 默认只把 scripts
# 目录放进模块搜索路径。这里补入项目根目录，确保可以正常导入 app 包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.core.redis import close_redis, get_redis_client
from app.core.security import hash_password
from app.models.category import Category
from app.models.department import Department
from app.models.discount_rule import DiscountRule
from app.models.discount_rule_scope import DiscountRuleScope
from app.models.employee import Employee
from app.models.employee_detail import EmployeeDetail
from app.models.enums import (
    DiscountScheduleType,
    DiscountScopeType,
    DiscountType,
    EmployeeGender,
    EmployeeRole,
    EmploymentStatus,
    InventoryBatchStatus,
    ProductStatus,
    PurchaseStatus,
    SaleSource,
)
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store, StoreDepartment
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct

# 固定随机种子，使每次在全新数据库执行时都能得到相同、便于讲解的数据分布。
RANDOM_SEED = 20260930
# 演示数据覆盖今天以及此前 60 天，共 61 个自然日。
DEMO_DAYS = 60
# 新增员工共用的演示登录密码；已有店长账号及密码不会被修改。
DEMO_EMPLOYEE_PASSWORD = "MarketFlow2026!"
MONEY_STEP = Decimal("1")

# Windows 控制台可能使用 cp932，显式切换成 UTF-8，避免日语输出乱码。
if isinstance(sys.stdout, TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class ProductSeed:
    """描述一项需要创建的供应商目录商品和正式商品。"""

    department_code: str
    category_name: str
    supplier_index: int
    name: str
    unit_cost: int
    sale_price: int
    shelf_life_days: int
    warning_days: int
    low_stock_threshold: int


@dataclass
class BatchLedger:
    """保存生成销售记录时需要使用的批次库存账本。"""

    batch: InventoryBatch
    product: Product
    unit_cost: Decimal


DEPARTMENT_SEEDS = [
    ("PRODUCE", "青果部"),
    ("MEAT", "精肉部"),
    ("SEAFOOD", "鮮魚部"),
    ("DELI", "惣菜部"),
]

CATEGORY_SEEDS = {
    "PRODUCE": ["野菜", "果物", "きのこ・山菜"],
    "MEAT": ["牛肉", "豚肉", "鶏肉", "加工肉"],
    "SEAFOOD": ["鮮魚", "刺身", "貝類", "水産加工品"],
    "DELI": ["弁当", "揚げ物", "サラダ", "寿司"],
}

EMPLOYEE_SEEDS = [
    ("EMP00002", "佐藤 健太", EmployeeRole.REGULAR_EMPLOYEE, "PRODUCE", EmployeeGender.MALE),
    ("EMP00003", "鈴木 美咲", EmployeeRole.CONTRACT_WORKER, "PRODUCE", EmployeeGender.FEMALE),
    ("EMP00004", "高橋 大輔", EmployeeRole.REGULAR_EMPLOYEE, "MEAT", EmployeeGender.MALE),
    ("EMP00005", "田中 愛", EmployeeRole.CONTRACT_WORKER, "MEAT", EmployeeGender.FEMALE),
    ("EMP00006", "伊藤 拓海", EmployeeRole.REGULAR_EMPLOYEE, "SEAFOOD", EmployeeGender.MALE),
    ("EMP00007", "渡辺 さくら", EmployeeRole.CONTRACT_WORKER, "SEAFOOD", EmployeeGender.FEMALE),
    ("EMP00008", "山本 翔太", EmployeeRole.REGULAR_EMPLOYEE, "DELI", EmployeeGender.MALE),
    ("EMP00009", "中村 結衣", EmployeeRole.CONTRACT_WORKER, "DELI", EmployeeGender.FEMALE),
]

SUPPLIER_SEEDS = [
    ("SUP00001", "関東青果流通株式会社", "小林 誠", "03-5550-1101", "東京都大田区東海3-2-1"),
    ("SUP00002", "信州フレッシュ農園", "丸山 直子", "0263-55-2202", "長野県松本市島内1250"),
    (
        "SUP00003",
        "東京ミートサービス株式会社",
        "阿部 和也",
        "03-5550-3303",
        "東京都品川区八潮2-8-4",
    ),
    ("SUP00004", "北海食肉産業株式会社", "佐々木 実", "011-555-4404", "北海道札幌市東区北丘珠"),
    ("SUP00005", "築地水産パートナーズ", "石井 浩", "03-5550-5505", "東京都江東区豊洲6-5-1"),
    ("SUP00006", "三陸海産株式会社", "菊池 真由", "0226-55-6606", "宮城県気仙沼市魚市場前"),
    (
        "SUP00007",
        "日本デリカフーズ株式会社",
        "清水 亮",
        "048-555-7707",
        "埼玉県さいたま市北区吉野町",
    ),
    ("SUP00008", "まごころ惣菜センター", "加藤 恵", "047-555-8808", "千葉県船橋市高瀬町"),
]

# 商品名末尾に供应商記号を付けず、日本の売場で自然に見える名称を使用する。
# 本システムでは一つの正式商品が一つの供应商商品目录に対応するため、主キーで区別できる。
PRODUCT_SEEDS = [
    ProductSeed("PRODUCE", "野菜", 0, "北海道産じゃがいも", 98, 198, 14, 3, 18),
    ProductSeed("PRODUCE", "野菜", 0, "北海道産たまねぎ", 88, 178, 21, 4, 20),
    ProductSeed("PRODUCE", "野菜", 1, "長野県産レタス", 118, 238, 7, 2, 12),
    ProductSeed("PRODUCE", "野菜", 1, "群馬県産キャベツ", 108, 218, 10, 2, 14),
    ProductSeed("PRODUCE", "果物", 0, "青森県産りんご", 138, 278, 20, 4, 15),
    ProductSeed("PRODUCE", "果物", 1, "山梨県産ぶどう", 298, 598, 8, 2, 10),
    ProductSeed("PRODUCE", "果物", 0, "フィリピン産バナナ", 89, 178, 7, 2, 16),
    ProductSeed("PRODUCE", "きのこ・山菜", 1, "長野県産ぶなしめじ", 78, 158, 10, 2, 12),
    ProductSeed("PRODUCE", "きのこ・山菜", 1, "新潟県産まいたけ", 108, 218, 9, 2, 10),
    ProductSeed("PRODUCE", "野菜", 0, "熊本県産トマト", 148, 298, 8, 2, 12),
    ProductSeed("MEAT", "牛肉", 2, "国産牛切り落とし 200g", 398, 798, 5, 2, 10),
    ProductSeed("MEAT", "牛肉", 3, "北海道産牛ももステーキ", 548, 1098, 6, 2, 8),
    ProductSeed("MEAT", "豚肉", 2, "国産豚バラ薄切り 250g", 268, 538, 4, 1, 12),
    ProductSeed("MEAT", "豚肉", 3, "国産豚ロース生姜焼き用", 298, 598, 5, 1, 10),
    ProductSeed("MEAT", "鶏肉", 2, "国産若鶏もも肉 300g", 238, 478, 4, 1, 14),
    ProductSeed("MEAT", "鶏肉", 3, "国産若鶏むね肉 300g", 148, 298, 4, 1, 16),
    ProductSeed("MEAT", "加工肉", 2, "あらびきポークウインナー", 178, 358, 21, 5, 12),
    ProductSeed("MEAT", "加工肉", 3, "ロースハムスライス", 158, 318, 18, 4, 10),
    ProductSeed("MEAT", "加工肉", 2, "ベーコンスライス", 198, 398, 20, 4, 10),
    ProductSeed("MEAT", "豚肉", 3, "国産豚ひき肉 300g", 218, 438, 3, 1, 12),
    ProductSeed("SEAFOOD", "鮮魚", 4, "宮城県産生銀鮭 2切", 298, 598, 3, 1, 10),
    ProductSeed("SEAFOOD", "鮮魚", 5, "長崎県産真あじ 2尾", 248, 498, 2, 1, 10),
    ProductSeed("SEAFOOD", "鮮魚", 4, "北海道産生たら 2切", 278, 558, 3, 1, 9),
    ProductSeed("SEAFOOD", "刺身", 4, "本まぐろ赤身刺身", 398, 798, 2, 1, 8),
    ProductSeed("SEAFOOD", "刺身", 5, "サーモン刺身用", 348, 698, 2, 1, 8),
    ProductSeed("SEAFOOD", "貝類", 5, "北海道産ほたて貝柱", 448, 898, 4, 1, 7),
    ProductSeed("SEAFOOD", "貝類", 4, "広島県産加熱用かき", 328, 658, 3, 1, 7),
    ProductSeed("SEAFOOD", "水産加工品", 5, "塩さばフィーレ", 198, 398, 14, 3, 12),
    ProductSeed("SEAFOOD", "水産加工品", 4, "釜揚げしらす", 178, 358, 7, 2, 10),
    ProductSeed("SEAFOOD", "水産加工品", 5, "辛子明太子", 298, 598, 12, 3, 9),
    ProductSeed("DELI", "弁当", 6, "幕の内弁当", 248, 498, 1, 1, 12),
    ProductSeed("DELI", "弁当", 7, "鶏そぼろ弁当", 198, 398, 1, 1, 14),
    ProductSeed("DELI", "弁当", 6, "焼鮭弁当", 278, 558, 1, 1, 10),
    ProductSeed("DELI", "揚げ物", 7, "若鶏の唐揚げ 5個", 188, 378, 2, 1, 16),
    ProductSeed("DELI", "揚げ物", 6, "北海道男爵コロッケ 3個", 128, 258, 2, 1, 14),
    ProductSeed("DELI", "揚げ物", 7, "ロースとんかつ", 248, 498, 2, 1, 10),
    ProductSeed("DELI", "サラダ", 6, "ポテトサラダ", 148, 298, 3, 1, 12),
    ProductSeed("DELI", "サラダ", 7, "蒸し鶏のごまサラダ", 198, 398, 2, 1, 10),
    ProductSeed("DELI", "寿司", 6, "にぎり寿司 8貫", 398, 798, 1, 1, 8),
    ProductSeed("DELI", "寿司", 7, "海鮮太巻き", 298, 598, 1, 1, 8),
]


def money(value: Decimal | int | float | str) -> Decimal:
    """把金额统一为数据库使用的两位小数。"""

    return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def batch_status(batch: InventoryBatch, product: Product, today: date) -> InventoryBatchStatus:
    """按照项目现有优先级计算最终批次状态。"""

    if batch.remaining_quantity == 0:
        return InventoryBatchStatus.SOLD_OUT
    if batch.expiration_date is not None and batch.expiration_date < today:
        return InventoryBatchStatus.EXPIRED
    if (
        batch.expiration_date is not None
        and product.expiry_warning_days is not None
        and batch.expiration_date <= today + timedelta(days=product.expiry_warning_days)
    ):
        return InventoryBatchStatus.NEAR_EXPIRY
    return InventoryBatchStatus.AVAILABLE


async def assert_business_tables_are_empty(db: AsyncSession) -> None:
    """在写入前确认业务表为空，避免演示脚本覆盖用户数据。"""

    models = [
        Department,
        Category,
        Supplier,
        SupplierProduct,
        Product,
        Purchase,
        PurchaseItem,
        InventoryBatch,
        Sale,
        SaleItem,
        DiscountRule,
        DiscountRuleScope,
    ]
    occupied_tables: list[str] = []
    for model in models:
        count = int(await db.scalar(select(func.count()).select_from(model)) or 0)
        if count > 0:
            occupied_tables.append(f"{model.__tablename__}({count})")

    if occupied_tables:
        joined_tables = "、".join(occupied_tables)
        raise RuntimeError(
            f"演示数据未写入：以下业务表已有数据：{joined_tables}。"
            "为保护现有数据，本脚本不会自动清空数据库。"
        )


# region 创建基础资料
async def create_master_data(
    db: AsyncSession,
    rng: random.Random,
    start_date: date,
) -> tuple[
    Employee,
    dict[str, Department],
    dict[tuple[str, str], Category],
    list[Employee],
    list[Supplier],
    list[Product],
]:
    """创建部门、分类、员工、供应商目录与正式商品。"""

    manager = await db.scalar(
        select(Employee).where(Employee.role == EmployeeRole.STORE_MANAGER).order_by(Employee.id)
    )
    if manager is None:
        raise RuntimeError("没有找到店长账号，请先运行 scripts/bootstrap_manager.py")

    if manager.store_id is None:
        raise RuntimeError("店长账号没有归属门店，请先配置门店")
    store = await db.get(Store, manager.store_id)
    if store is None:
        raise RuntimeError("店长归属门店不存在")
    store.name = "MarketFlow 高円寺店"

    # 创建四个日语部门及其商品分类。
    departments: dict[str, Department] = {}
    for code, name in DEPARTMENT_SEEDS:
        department = Department(code=code, name=name, is_active=True)
        departments[code] = department
        db.add(department)
    await db.flush()

    for department in departments.values():
        db.add(
            StoreDepartment(store_id=manager.store_id, department_id=department.id, is_active=True)
        )
    await db.flush()

    categories: dict[tuple[str, str], Category] = {}
    for department_code, category_names in CATEGORY_SEEDS.items():
        for category_name in category_names:
            category = Category(
                department_id=departments[department_code].id,
                name=category_name,
                is_active=True,
            )
            categories[(department_code, category_name)] = category
            db.add(category)
    await db.flush()

    # 演示员工可直接登录，便于展示不同部门的权限效果。
    shared_password_hash = hash_password(DEMO_EMPLOYEE_PASSWORD)
    employees: list[Employee] = []
    for index, (employee_no, name, role, department_code, gender) in enumerate(EMPLOYEE_SEEDS):
        employee = Employee(
            employee_no=employee_no,
            store_id=manager.store_id,
            name=name,
            password_hash=shared_password_hash,
            role=role,
            department_id=departments[department_code].id,
            is_active=True,
            must_change_password=False,
            last_login_at=datetime.combine(start_date + timedelta(days=55), time(9, 5)),
        )
        employee.detail = EmployeeDetail(
            gender=gender,
            birth_date=date(1988 + index, (index % 12) + 1, 8 + index),
            hire_date=date(2022 + index % 4, (index % 10) + 1, 1 + index),
            phone=f"090-{4100 + index:04d}-{6200 + index:04d}",
            address=f"東京都杉並区高円寺北{index + 1}-{index + 2}-{index + 3}",
            employment_status=EmploymentStatus.EMPLOYED,
        )
        employees.append(employee)
        db.add(employee)
    await db.flush()

    suppliers: list[Supplier] = []
    for supplier_no, name, contact_name, phone, address in SUPPLIER_SEEDS:
        supplier = Supplier(
            supplier_no=supplier_no,
            name=name,
            contact_name=contact_name,
            phone=phone,
            address=address,
            is_active=True,
        )
        suppliers.append(supplier)
        db.add(supplier)
    await db.flush()

    # 供应商目录与正式商品一一对应；价格在合理范围内做轻微随机差异。
    products: list[Product] = []
    for index, seed in enumerate(PRODUCT_SEEDS, start=1):
        category = categories[(seed.department_code, seed.category_name)]
        catalog_product = SupplierProduct(
            supplier_id=suppliers[seed.supplier_index].id,
            category_id=category.id,
            name=seed.name,
            unit_cost=money(seed.unit_cost),
            shelf_life_days=seed.shelf_life_days,
            is_active=True,
        )
        db.add(catalog_product)
        await db.flush()

        product = Product(
            product_no=f"P{index:05d}",
            name=seed.name,
            supplier_product_id=catalog_product.id,
            department_id=departments[seed.department_code].id,
            category_id=category.id,
            purchase_price=money(seed.unit_cost),
            sale_price=money(seed.sale_price),
            stock_quantity=0,
            expiry_warning_days=seed.warning_days,
            low_stock_threshold=seed.low_stock_threshold,
            status=ProductStatus.STOPPED if index == len(PRODUCT_SEEDS) else ProductStatus.ON_SALE,
            created_at=datetime.combine(start_date - timedelta(days=12), time(12)),
            updated_at=datetime.combine(start_date - timedelta(days=12), time(12)),
        )
        products.append(product)
        db.add(product)
    await db.flush()

    # 让少量主数据带有不同状态，前端筛选页面更容易演示。
    suppliers[-1].is_active = False
    employees[-1].is_active = False
    last_employee_detail = employees[-1].detail
    if last_employee_detail is None:
        raise RuntimeError("演示员工详情创建失败")
    last_employee_detail.employment_status = EmploymentStatus.ON_LEAVE
    last_employee_detail.address = "東京都江戸川区西葛西5-12-8"
    # 消耗一次随机数，明确表明主数据也由固定种子控制，便于以后扩充。
    rng.random()

    return manager, departments, categories, employees, suppliers, products


# endregion


# region 创建折扣规则
async def create_discount_rules(
    db: AsyncSession,
    manager: Employee,
    departments: dict[str, Department],
    products: list[Product],
    end_date: date,
) -> dict[str, DiscountRule]:
    """创建可展示四种动态状态的日语折扣规则。"""

    current_midnight = datetime.combine(end_date, time())
    rules = {
        "PRODUCE": DiscountRule(
            name="青果朝市10％OFF",
            department_id=departments["PRODUCE"].id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.9000"),
            schedule_type=DiscountScheduleType.DAILY,
            daily_start_time=time(9),
            daily_end_time=time(11, 30),
            is_active=True,
            created_by=manager.id,
        ),
        "MEAT": DiscountRule(
            name="週末お肉15％OFF",
            department_id=departments["MEAT"].id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.8500"),
            schedule_type=DiscountScheduleType.WEEKLY,
            daily_start_time=time(16),
            daily_end_time=time(20, 30),
            weekdays=[6, 7],
            is_active=True,
            created_by=manager.id,
        ),
        "SEAFOOD": DiscountRule(
            name="鮮魚夕市20％OFF",
            department_id=departments["SEAFOOD"].id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.8000"),
            schedule_type=DiscountScheduleType.DAILY,
            daily_start_time=time(18),
            daily_end_time=time(20, 45),
            is_active=True,
            created_by=manager.id,
        ),
        "DELI": DiscountRule(
            name="惣菜閉店前30％OFF",
            department_id=departments["DELI"].id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.7000"),
            schedule_type=DiscountScheduleType.DAILY,
            daily_start_time=time(19),
            daily_end_time=time(20, 55),
            is_active=True,
            created_by=manager.id,
        ),
        "ENDED": DiscountRule(
            name="夏休み特別セール",
            department_id=departments["PRODUCE"].id,
            discount_type=DiscountType.AMOUNT_OFF,
            discount_value=Decimal("30.0000"),
            schedule_type=DiscountScheduleType.ONCE,
            starts_at=current_midnight - timedelta(days=45),
            ends_at=current_midnight - timedelta(days=38),
            is_active=True,
            created_by=manager.id,
        ),
        "SCHEDULED": DiscountRule(
            name="来月のお客様感謝デー",
            department_id=departments["MEAT"].id,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("0.9000"),
            schedule_type=DiscountScheduleType.ONCE,
            starts_at=current_midnight + timedelta(days=7, hours=9),
            ends_at=current_midnight + timedelta(days=7, hours=20),
            is_active=True,
            created_by=manager.id,
        ),
        "DISABLED": DiscountRule(
            name="試験運用固定価格セール",
            department_id=departments["SEAFOOD"].id,
            discount_type=DiscountType.FIXED_PRICE,
            discount_value=Decimal("298.0000"),
            schedule_type=DiscountScheduleType.DAILY,
            daily_start_time=time(15),
            daily_end_time=time(18),
            is_active=False,
            created_by=manager.id,
        ),
    }
    db.add_all(rules.values())
    await db.flush()

    # 折扣规则属于一个部门，但实际生效范围由具体商品关联决定。
    for key, rule in rules.items():
        if key in departments:
            department = departments[key]
        elif key == "ENDED":
            department = departments["PRODUCE"]
        elif key == "SCHEDULED":
            department = departments["MEAT"]
        else:
            department = departments["SEAFOOD"]
        for product in products:
            if product.department_id != department.id:
                continue
            db.add(
                DiscountRuleScope(
                    discount_rule_id=rule.id,
                    scope_type=DiscountScopeType.PRODUCT,
                    product_id=product.id,
                )
            )
    await db.flush()
    return rules


# endregion


# region 创建进货单和库存批次
async def create_purchases_and_batches(
    db: AsyncSession,
    rng: random.Random,
    start_date: date,
    end_date: date,
    departments: dict[str, Department],
    employees: list[Employee],
    suppliers: list[Supplier],
    products: list[Product],
    *,
    interval_days: int = 3,
    number_prefix: str = "",
) -> tuple[list[Purchase], list[BatchLedger]]:
    """创建两个月进货历史，并为已到货明细生成库存批次。"""

    employee_by_department: dict[int, Employee] = {}
    for employee in employees:
        if employee.role == EmployeeRole.REGULAR_EMPLOYEE:
            if employee.department_id is None:
                raise RuntimeError("正式员工必须属于一个部门")
            employee_by_department[employee.department_id] = employee

    products_by_department: dict[int, list[Product]] = defaultdict(list)
    product_seed_by_number = {
        f"P{index:05d}": seed for index, seed in enumerate(PRODUCT_SEEDS, start=1)
    }
    for product in products:
        products_by_department[product.department_id].append(product)

    purchases: list[Purchase] = []
    ledgers: list[BatchLedger] = []
    purchase_counter = 1
    batch_counter = 1

    # 从销售开始日前两天开始下单，使第一天营业时已经有可售库存。
    order_date = start_date - timedelta(days=2)
    while order_date <= end_date:
        for department_index, (department_code, _name) in enumerate(DEPARTMENT_SEEDS):
            department = departments[department_code]
            department_products = products_by_department[department.id]
            ordered_at = datetime.combine(order_date, time(9, 30 + department_index * 5))
            expected_arrival_at = datetime.combine(
                order_date + timedelta(days=2),
                time(12),
            )
            arrived = expected_arrival_at <= business_now()
            receiver = employee_by_department[department.id]

            # 每次轮换选择四种商品，确保全部商品在两个月内都有多个批次。
            rotation = ((order_date - start_date).days + department_index * 2) % len(
                department_products
            )
            selected_products = [
                department_products[(rotation + offset * 2) % len(department_products)]
                for offset in range(4)
            ]

            purchase = Purchase(
                purchase_no=f"{number_prefix}PO{order_date:%Y%m%d}-{purchase_counter:04d}",
                department_id=department.id,
                created_by=receiver.id,
                received_by=receiver.id if arrived else None,
                ordered_at=ordered_at,
                expected_arrival_at=expected_arrival_at,
                arrived_at=expected_arrival_at if arrived else None,
                total_amount=Decimal("0.00"),
                status=PurchaseStatus.ARRIVED if arrived else PurchaseStatus.PENDING,
                created_at=ordered_at,
                updated_at=expected_arrival_at if arrived else ordered_at,
            )
            db.add(purchase)
            await db.flush()

            purchase_total = Decimal("0.00")
            for product in selected_products:
                seed = product_seed_by_number[product.product_no]
                quantity = rng.randint(24, 46)
                # 模拟供应报价小幅波动，但正式商品当前进货价保持最新目录价。
                price_factor = Decimal(str(rng.choice([0.96, 0.98, 1.00, 1.02, 1.04])))
                unit_cost = money(product.purchase_price * price_factor)
                subtotal = money(unit_cost * quantity)
                production_date = expected_arrival_at.date() - timedelta(
                    days=rng.randint(0, min(2, max(seed.shelf_life_days - 1, 0)))
                )
                expiration_date = production_date + timedelta(days=seed.shelf_life_days)

                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=product.id if arrived else product.id,
                    supplier_product_id=product.supplier_product_id,
                    supplier_id=suppliers[seed.supplier_index].id,
                    product_no_snapshot=product.product_no,
                    product_name_snapshot=product.name,
                    supplier_name_snapshot=suppliers[seed.supplier_index].name,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    subtotal=subtotal,
                    production_date=production_date,
                    expiration_date=expiration_date,
                    created_at=ordered_at,
                )
                db.add(purchase_item)
                await db.flush()
                purchase_total += subtotal

                if arrived:
                    batch = InventoryBatch(
                        batch_no=f"{number_prefix}LOT{expected_arrival_at:%Y%m%d}-{batch_counter:05d}",
                        product_id=product.id,
                        purchase_item_id=purchase_item.id,
                        production_date=production_date,
                        expiration_date=expiration_date,
                        initial_quantity=quantity,
                        remaining_quantity=quantity,
                        status=InventoryBatchStatus.AVAILABLE,
                        arrived_at=expected_arrival_at,
                        created_at=expected_arrival_at,
                        updated_at=expected_arrival_at,
                    )
                    db.add(batch)
                    ledgers.append(BatchLedger(batch=batch, product=product, unit_cost=unit_cost))
                    batch_counter += 1

            purchase.total_amount = money(purchase_total)
            purchases.append(purchase)
            purchase_counter += 1

        # 每三天集中补货一次，便于前端趋势图呈现稳定但不完全均匀的变化。
        order_date += timedelta(days=interval_days)

    await db.flush()
    return purchases, ledgers


# endregion


# region 创建销售记录
def find_sale_discount(
    product: Product,
    sold_at: datetime,
    rules: dict[str, DiscountRule],
    department_code_by_id: dict[int, str],
) -> DiscountRule | None:
    """按照部门、星期和成交时间查找演示销售应使用的折扣规则。"""

    department_code = department_code_by_id[product.department_id]
    sale_time = sold_at.time()
    if department_code == "PRODUCE" and time(9) <= sale_time < time(11, 30):
        return rules["PRODUCE"]
    if (
        department_code == "MEAT"
        and sold_at.isoweekday() in {6, 7}
        and time(16) <= sale_time < time(20, 30)
    ):
        return rules["MEAT"]
    if department_code == "SEAFOOD" and time(18) <= sale_time < time(20, 45):
        return rules["SEAFOOD"]
    if department_code == "DELI" and time(19) <= sale_time < time(20, 55):
        return rules["DELI"]
    return None


def discounted_unit_price(product: Product, rule: DiscountRule | None) -> Decimal:
    """根据命中的折扣规则计算单件成交价。"""

    original_price = money(product.sale_price)
    if rule is None:
        return original_price
    if rule.discount_type == DiscountType.PERCENTAGE:
        return money(original_price * rule.discount_value)
    if rule.discount_type == DiscountType.AMOUNT_OFF:
        return max(Decimal("0.00"), money(original_price - rule.discount_value))
    return min(original_price, money(rule.discount_value))


async def create_sales(
    db: AsyncSession,
    rng: random.Random,
    start_date: date,
    end_date: date,
    departments: dict[str, Department],
    employees: list[Employee],
    products: list[Product],
    ledgers: list[BatchLedger],
    rules: dict[str, DiscountRule],
    *,
    volume_multiplier: int = 1,
    number_prefix: str = "",
) -> list[Sale]:
    """按批次先进先出扣减库存，并创建约两个月的销售小票。"""

    department_code_by_id = {department.id: code for code, department in departments.items()}
    ledgers_by_product: dict[int, list[BatchLedger]] = defaultdict(list)
    for ledger in ledgers:
        ledgers_by_product[ledger.product.id].append(ledger)
    for product_ledgers in ledgers_by_product.values():
        product_ledgers.sort(key=lambda item: (item.batch.expiration_date, item.batch.arrived_at))

    sales: list[Sale] = []
    sale_counter = 1
    current_date = start_date
    active_products = [item for item in products if item.status == ProductStatus.ON_SALE]

    while current_date <= end_date:
        # 半年数据只扫描当天可用的批次，避免每笔销售遍历全部历史库存。
        day_end = datetime.combine(current_date, time.max)
        daily_ledgers = {
            product_id: [
                ledger
                for ledger in product_ledgers
                if ledger.batch.arrived_at <= day_end
                and (
                    ledger.batch.expiration_date is None
                    or ledger.batch.expiration_date >= current_date
                )
            ]
            for product_id, product_ledgers in ledgers_by_product.items()
        }
        # 周末客流高于工作日；月底最后一天数据保持较少，便于现场继续扫码演示。
        if current_date == end_date:
            daily_sale_count = 12
        elif current_date.isoweekday() in {6, 7}:
            daily_sale_count = rng.randint(32, 38)
        else:
            daily_sale_count = rng.randint(23, 29)

        for _sale_index in range(daily_sale_count * volume_multiplier):
            sold_at = datetime.combine(
                current_date,
                time(
                    hour=rng.randint(9, 20),
                    minute=rng.randint(0, 59),
                    second=rng.randint(0, 59),
                ),
            )

            # 只把当时已经到货、尚未到期且仍有库存的商品加入本次候选列表。
            available_products: list[Product] = []
            for product in active_products:
                has_available_batch = False
                for ledger in daily_ledgers[product.id]:
                    batch = ledger.batch
                    if (
                        batch.arrived_at <= sold_at
                        and batch.remaining_quantity > 0
                        and (batch.expiration_date is None or batch.expiration_date >= current_date)
                    ):
                        has_available_batch = True
                        break
                if has_available_batch:
                    available_products.append(product)

            if not available_products:
                continue

            requested_product_count = min(rng.randint(1, 4), len(available_products))
            selected_products = rng.sample(available_products, requested_product_count)
            sale_items: list[SaleItem] = []

            for product in selected_products:
                requested_quantity = rng.choices([1, 2, 3, 4], weights=[52, 30, 13, 5])[0]
                remaining_request = requested_quantity
                rule = find_sale_discount(
                    product,
                    sold_at,
                    rules,
                    department_code_by_id,
                )
                unit_price = discounted_unit_price(product, rule)

                # 一次商品购买可能跨越两个批次，因此每个实际扣减批次生成一条销售明细。
                for ledger in daily_ledgers[product.id]:
                    batch = ledger.batch
                    if remaining_request == 0:
                        break
                    if (
                        batch.arrived_at > sold_at
                        or batch.remaining_quantity == 0
                        or (
                            batch.expiration_date is not None
                            and batch.expiration_date < current_date
                        )
                    ):
                        continue

                    deducted_quantity = min(remaining_request, batch.remaining_quantity)
                    batch.remaining_quantity -= deducted_quantity
                    remaining_request -= deducted_quantity
                    original_subtotal = money(product.sale_price * deducted_quantity)
                    subtotal = money(unit_price * deducted_quantity)
                    cost_subtotal = money(ledger.unit_cost * deducted_quantity)

                    sale_items.append(
                        SaleItem(
                            product_id=product.id,
                            inventory_batch_id=batch.id,
                            product_no_snapshot=product.product_no,
                            product_name_snapshot=product.name,
                            department_id=product.department_id,
                            quantity=deducted_quantity,
                            original_unit_price=money(product.sale_price),
                            unit_price=unit_price,
                            discount_amount=money(original_subtotal - subtotal),
                            discount_rule_id=rule.id if rule is not None else None,
                            discount_rule_name_snapshot=rule.name if rule is not None else None,
                            discount_type_snapshot=(
                                rule.discount_type.value if rule is not None else None
                            ),
                            discount_value_snapshot=(
                                rule.discount_value if rule is not None else None
                            ),
                            unit_cost=ledger.unit_cost,
                            subtotal=subtotal,
                            cost_subtotal=cost_subtotal,
                        )
                    )

            if not sale_items:
                continue

            original_total = money(
                sum(item.original_unit_price * item.quantity for item in sale_items)
            )
            total_amount = money(sum(item.subtotal for item in sale_items))
            total_cost = money(sum(item.cost_subtotal for item in sale_items))
            sale = Sale(
                sale_no=f"{number_prefix}S{current_date:%Y%m%d}-{sale_counter:06d}",
                sold_at=sold_at,
                total_amount=total_amount,
                original_total_amount=original_total,
                discount_amount=money(original_total - total_amount),
                total_cost=total_cost,
                gross_profit=money(total_amount - total_cost),
                source=SaleSource.DEMO_SEED,
                items=sale_items,
                created_at=sold_at,
            )
            sales.append(sale)
            db.add(sale)
            sale_counter += 1

        current_date += timedelta(days=1)

    await db.flush()

    # 销售全部生成后统一回写批次状态与商品汇总库存。
    today = end_date
    stock_by_product: dict[int, int] = defaultdict(int)
    for ledger in ledgers:
        ledger.batch.status = batch_status(ledger.batch, ledger.product, today)
        ledger.batch.updated_at = datetime.combine(today, time(0, 5))
        stock_by_product[ledger.product.id] += ledger.batch.remaining_quantity
    for product in products:
        product.stock_quantity = stock_by_product[product.id]
        product.updated_at = datetime.combine(today, time(0, 10))

    # 保留一个库存不一致示例会降低面试可信度，因此所有商品均严格等于批次剩余量之和。
    await db.flush()
    # employees 参数用于表明销售由店内员工负责，但当前 Sale 模型尚未保存收银员字段。
    _ = employees
    return sales


# endregion


# region 创建操作审计记录
async def create_audit_logs(
    db: AsyncSession,
    manager: Employee,
    employees: list[Employee],
    suppliers: list[Supplier],
    products: list[Product],
    purchases: list[Purchase],
    ledgers: list[BatchLedger],
    sales: list[Sale],
    rules: dict[str, DiscountRule],
) -> None:
    """为主要新增操作创建可供审计页面展示的记录。"""

    audit_logs: list[OperationAuditLog] = []
    master_data_created_at = business_now() - timedelta(days=DEMO_DAYS + 14)
    for employee_index, employee in enumerate(employees):
        audit_logs.append(
            OperationAuditLog(
                employee_id=manager.id,
                module="employee",
                action="create",
                target_type="employee",
                target_id=employee.id,
                after_data={"employee_no": employee.employee_no, "name": employee.name},
                reason="面接用デモデータの初期登録",
                created_at=master_data_created_at + timedelta(minutes=employee_index),
            )
        )
    for supplier_index, supplier in enumerate(suppliers):
        audit_logs.append(
            OperationAuditLog(
                employee_id=manager.id,
                module="supplier",
                action="create",
                target_type="supplier",
                target_id=supplier.id,
                after_data={"supplier_no": supplier.supplier_no, "name": supplier.name},
                reason="取引先マスタの初期登録",
                created_at=master_data_created_at + timedelta(hours=1, minutes=supplier_index),
            )
        )
    for product in products:
        audit_logs.append(
            OperationAuditLog(
                employee_id=manager.id,
                module="product",
                action="create_from_purchase",
                target_type="product",
                target_id=product.id,
                after_data={"product_no": product.product_no, "name": product.name},
                reason="初回入荷による商品マスタ登録",
                created_at=product.created_at,
            )
        )
    for purchase in purchases:
        audit_logs.append(
            OperationAuditLog(
                employee_id=purchase.created_by,
                module="purchase",
                action="create",
                target_type="purchase",
                target_id=purchase.id,
                after_data={
                    "purchase_no": purchase.purchase_no,
                    "status": purchase.status.value,
                    "total_amount": str(purchase.total_amount),
                },
                reason="定期発注",
                created_at=purchase.ordered_at,
            )
        )
        if purchase.status == PurchaseStatus.ARRIVED:
            audit_logs.append(
                OperationAuditLog(
                    employee_id=purchase.received_by,
                    module="purchase",
                    action="auto_receive",
                    target_type="purchase",
                    target_id=purchase.id,
                    before_data={"status": PurchaseStatus.PENDING.value},
                    after_data={"status": PurchaseStatus.ARRIVED.value},
                    reason="予定到着時刻に基づく自動検収",
                    created_at=purchase.arrived_at,
                )
            )
    # 每个到货批次都需要一条库存增加流水；页面会把 before_data 为空视为从 0 入库。
    for ledger in ledgers:
        batch = ledger.batch
        audit_logs.append(
            OperationAuditLog(
                employee_id=None,
                module="inventory",
                action="create_batch",
                target_type="inventory_batch",
                target_id=batch.id,
                before_data=None,
                after_data={
                    "batch_no": batch.batch_no,
                    "product_id": batch.product_id,
                    "purchase_item_id": batch.purchase_item_id,
                    "remaining_quantity": batch.initial_quantity,
                    "expiration_date": (
                        batch.expiration_date.isoformat()
                        if batch.expiration_date is not None
                        else None
                    ),
                    "status": InventoryBatchStatus.AVAILABLE.value,
                },
                reason="入荷検収による在庫追加",
                created_at=batch.arrived_at,
            )
        )
    for rule_index, rule in enumerate(rules.values()):
        audit_logs.append(
            OperationAuditLog(
                employee_id=manager.id,
                module="discount",
                action="create",
                target_type="discount_rule",
                target_id=rule.id,
                after_data={"name": rule.name, "is_active": rule.is_active},
                reason="販売促進ルールの登録",
                created_at=master_data_created_at + timedelta(days=1, minutes=rule_index),
            )
        )
    for sale in sales:
        audit_logs.append(
            OperationAuditLog(
                employee_id=None,
                module="sale",
                action="create",
                target_type="sale",
                target_id=sale.id,
                after_data={
                    "sale_no": sale.sale_no,
                    "total_amount": str(sale.total_amount),
                    "discount_amount": str(sale.discount_amount),
                },
                reason="POSレジによる販売登録",
                created_at=sale.sold_at,
            )
        )

    # 按成交时间重放每一条销售明细，计算每个批次在扣减前后的准确剩余数量。
    running_quantities = {ledger.batch.id: ledger.batch.initial_quantity for ledger in ledgers}
    ledger_by_batch_id = {ledger.batch.id: ledger for ledger in ledgers}
    for sale in sorted(sales, key=lambda item: (item.sold_at, item.id)):
        for sale_item in sorted(sale.items, key=lambda item: item.id):
            batch_id = sale_item.inventory_batch_id
            if batch_id is None:
                continue
            ledger = ledger_by_batch_id[batch_id]
            before_quantity = running_quantities[batch_id]
            after_quantity = before_quantity - sale_item.quantity
            if after_quantity < 0:
                raise RuntimeError(f"批次 {ledger.batch.batch_no} 的演示销售数量超过库存")
            running_quantities[batch_id] = after_quantity
            after_status = (
                InventoryBatchStatus.SOLD_OUT
                if after_quantity == 0
                else InventoryBatchStatus.AVAILABLE
            )
            audit_logs.append(
                OperationAuditLog(
                    employee_id=None,
                    module="inventory",
                    action="sale_deduction",
                    target_type="inventory_batch",
                    target_id=batch_id,
                    before_data={"remaining_quantity": before_quantity},
                    after_data={
                        "remaining_quantity": after_quantity,
                        "status": after_status.value,
                        "deducted_quantity": sale_item.quantity,
                        "sale_id": sale.id,
                        "sale_item_id": sale_item.id,
                    },
                    reason="POSレジ販売による在庫減少",
                    created_at=sale.sold_at,
                )
            )

    # 重放销售得到的最终数量必须与库存批次表一致，否则整批演示数据回滚。
    for ledger in ledgers:
        if running_quantities[ledger.batch.id] != ledger.batch.remaining_quantity:
            raise RuntimeError(f"批次 {ledger.batch.batch_no} 的库存流水与最终库存不一致")
    db.add_all(audit_logs)
    await db.flush()


# endregion


# region 执行与结果验证
async def collect_counts(db: AsyncSession) -> dict[str, int]:
    """统计本次演示数据涉及的主要表记录数。"""

    models = [
        Department,
        Category,
        Employee,
        Supplier,
        SupplierProduct,
        Product,
        Purchase,
        PurchaseItem,
        InventoryBatch,
        DiscountRule,
        DiscountRuleScope,
        Sale,
        SaleItem,
        OperationAuditLog,
    ]
    counts: dict[str, int] = {}
    for model in models:
        counts[model.__tablename__] = int(
            await db.scalar(select(func.count()).select_from(model)) or 0
        )
    return counts


async def clear_project_response_cache() -> int:
    """清除可能保存了空列表的项目接口缓存，并返回删除键数量。"""

    client = get_redis_client()
    if client is None:
        return 0

    cache_keys = [key async for key in client.scan_iter(match="fastapi-cache:*")]
    if not cache_keys:
        return 0
    return int(await client.delete(*cache_keys))


async def backfill_inventory_movement_logs() -> tuple[int, int]:
    """为已经生成的演示批次和销售明细补充库存变动流水。"""

    async with async_session_factory() as db:
        existing_count = int(
            await db.scalar(
                select(func.count())
                .select_from(OperationAuditLog)
                .where(
                    OperationAuditLog.module == "inventory",
                    OperationAuditLog.action.in_(("create_batch", "sale_deduction")),
                )
            )
            or 0
        )
        if existing_count > 0:
            raise RuntimeError(
                f"数据库中已经存在 {existing_count} 条进货或销售库存流水，已停止补写以避免重复"
            )

        batch_result = await db.scalars(
            select(InventoryBatch)
            .options(selectinload(InventoryBatch.product))
            .order_by(InventoryBatch.arrived_at, InventoryBatch.id)
        )
        batches = list(batch_result.all())
        sale_result = await db.scalars(
            select(Sale).options(selectinload(Sale.items)).order_by(Sale.sold_at, Sale.id)
        )
        sales = list(sale_result.all())
        if not batches:
            raise RuntimeError("数据库中没有库存批次，无法补写库存流水")

        ledgers = [
            BatchLedger(batch=batch, product=batch.product, unit_cost=Decimal("0.00"))
            for batch in batches
        ]
        running_quantities = {batch.id: batch.initial_quantity for batch in batches}
        logs: list[OperationAuditLog] = []

        for batch in batches:
            logs.append(
                OperationAuditLog(
                    employee_id=None,
                    module="inventory",
                    action="create_batch",
                    target_type="inventory_batch",
                    target_id=batch.id,
                    before_data=None,
                    after_data={
                        "batch_no": batch.batch_no,
                        "product_id": batch.product_id,
                        "purchase_item_id": batch.purchase_item_id,
                        "remaining_quantity": batch.initial_quantity,
                        "expiration_date": (
                            batch.expiration_date.isoformat()
                            if batch.expiration_date is not None
                            else None
                        ),
                        "status": InventoryBatchStatus.AVAILABLE.value,
                    },
                    reason="入荷検収による在庫追加",
                    created_at=batch.arrived_at,
                )
            )

        sale_deduction_count = 0
        for sale in sales:
            for sale_item in sorted(sale.items, key=lambda item: item.id):
                batch_id = sale_item.inventory_batch_id
                if batch_id is None:
                    continue
                before_quantity = running_quantities[batch_id]
                after_quantity = before_quantity - sale_item.quantity
                if after_quantity < 0:
                    raise RuntimeError(f"批次 ID {batch_id} 的销售数量超过初始库存")
                running_quantities[batch_id] = after_quantity
                after_status = (
                    InventoryBatchStatus.SOLD_OUT
                    if after_quantity == 0
                    else InventoryBatchStatus.AVAILABLE
                )
                logs.append(
                    OperationAuditLog(
                        employee_id=None,
                        module="inventory",
                        action="sale_deduction",
                        target_type="inventory_batch",
                        target_id=batch_id,
                        before_data={"remaining_quantity": before_quantity},
                        after_data={
                            "remaining_quantity": after_quantity,
                            "status": after_status.value,
                            "deducted_quantity": sale_item.quantity,
                            "sale_id": sale.id,
                            "sale_item_id": sale_item.id,
                        },
                        reason="POSレジ販売による在庫減少",
                        created_at=sale.sold_at,
                    )
                )
                sale_deduction_count += 1

        batch_by_id = {batch.id: batch for batch in batches}
        for ledger in ledgers:
            batch = batch_by_id[ledger.batch.id]
            if running_quantities[batch.id] != batch.remaining_quantity:
                raise RuntimeError(f"批次 {batch.batch_no} 的重放库存与当前库存不一致")

        db.add_all(logs)
        await db.commit()
        return len(batches), sale_deduction_count


async def seed_japanese_demo_data() -> None:
    """在一个事务中生成并提交全部日语演示数据。"""

    rng = random.Random(RANDOM_SEED)
    end_date = business_now().date()
    start_date = end_date - timedelta(days=DEMO_DAYS)

    async with async_session_factory() as db:
        await assert_business_tables_are_empty(db)
        try:
            (
                manager,
                departments,
                categories,
                employees,
                suppliers,
                products,
            ) = await create_master_data(db, rng, start_date)
            rules = await create_discount_rules(db, manager, departments, products, end_date)
            purchases, ledgers = await create_purchases_and_batches(
                db,
                rng,
                start_date,
                end_date,
                departments,
                employees,
                suppliers,
                products,
            )
            sales = await create_sales(
                db,
                rng,
                start_date,
                end_date,
                departments,
                employees,
                products,
                ledgers,
                rules,
            )
            await create_audit_logs(
                db,
                manager,
                employees,
                suppliers,
                products,
                purchases,
                ledgers,
                sales,
                rules,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        counts = await collect_counts(db)
        try:
            cleared_cache_count = await clear_project_response_cache()
        except Exception as error:
            # 缓存清理失败不影响已经成功提交的数据库数据。
            cleared_cache_count = 0
            print(f"缓存清理失败，请重启后端或等待缓存过期：{error}")
        print("日语演示数据生成完成")
        print(f"模拟期间：{start_date:%Y-%m-%d} ～ {end_date:%Y-%m-%d}")
        for table_name, count in counts.items():
            print(f"{table_name}: {count}")
        print(f"已清除接口缓存键：{cleared_cache_count}")
        print(f"演示员工统一密码：{DEMO_EMPLOYEE_PASSWORD}")
        print("已有店长账号及密码未作修改。")


async def main() -> None:
    """运行演示数据初始化并在结束后释放数据库连接池。"""

    try:
        parser = argparse.ArgumentParser(description="生成或补充 MarketFlow 日语演示数据")
        parser.add_argument(
            "--backfill-inventory-movements",
            action="store_true",
            help="为已有演示批次和销售记录补充库存变动流水",
        )
        arguments = parser.parse_args()
        if arguments.backfill_inventory_movements:
            batch_count, deduction_count = await backfill_inventory_movement_logs()
            print(f"已补充进货入库流水：{batch_count} 条")
            print(f"已补充销售出库流水：{deduction_count} 条")
        else:
            await seed_japanese_demo_data()
            from scripts.normalize_demo_data import normalize

            await normalize()
    finally:
        await async_engine.dispose()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())


# endregion
