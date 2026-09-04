"""生成 MarketFlow 第一版演示数据。"""

import asyncio
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import async_engine, async_session_factory
from app.core.security import hash_password
from app.crud.employees import create_employee
from app.models.category import Category
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import EmployeeRole, ProductStatus, SaleSource
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem

DEFAULT_PASSWORD = "123456"
RANDOM_SEED = 20260904

DEPARTMENT_DATA = [
    ("MEAT", "精肉部", "陈晓峰", "林可欣"),
    ("DELI", "熟食部", "周雅雯", "吴嘉俊"),
    ("FISH", "鲜鱼部", "许文博", "赵雨晴"),
    ("PRODUCE", "果蔬部", "刘思远", "孙梦琪"),
]

CATEGORY_DATA = {
    "MEAT": ["牛肉类", "猪肉及禽类"],
    "DELI": ["便当类", "熟食小菜"],
    "FISH": ["鱼类", "贝类"],
    "PRODUCE": ["水果类", "蔬菜类"],
}

# 商品编号、名称、部门代码、分类名称、进货价、销售价、初始库存。
PRODUCT_DATA = [
    ("P00001", "国产牛肉片", "MEAT", "牛肉类", "26.00", "39.80", 42),
    ("P00002", "黑毛和牛牛排", "MEAT", "牛肉类", "78.00", "118.00", 18),
    ("P00003", "猪五花肉", "MEAT", "猪肉及禽类", "19.50", "29.80", 55),
    ("P00004", "猪里脊肉", "MEAT", "猪肉及禽类", "23.00", "35.80", 31),
    ("P00005", "鲜嫩鸡腿肉", "MEAT", "猪肉及禽类", "11.50", "18.80", 64),
    ("P00006", "照烧鸡肉便当", "DELI", "便当类", "12.00", "22.80", 27),
    ("P00007", "鳗鱼便当", "DELI", "便当类", "22.00", "36.80", 14),
    ("P00008", "日式炸鸡块", "DELI", "熟食小菜", "9.00", "16.80", 36),
    ("P00009", "土豆牛肉可乐饼", "DELI", "熟食小菜", "5.20", "9.80", 48),
    ("P00010", "海带豆腐沙拉", "DELI", "熟食小菜", "6.50", "12.80", 22),
    ("P00011", "挪威三文鱼切片", "FISH", "鱼类", "32.00", "49.80", 25),
    ("P00012", "盐烤青花鱼", "FISH", "鱼类", "16.00", "25.80", 33),
    ("P00013", "鲜活真鲷", "FISH", "鱼类", "38.00", "58.00", 12),
    ("P00014", "北海道扇贝", "FISH", "贝类", "29.00", "45.80", 20),
    ("P00015", "蒜蓉花蛤", "FISH", "贝类", "12.50", "21.80", 39),
    ("P00016", "青森红富士苹果", "PRODUCE", "水果类", "5.50", "9.80", 72),
    ("P00017", "菲律宾香蕉", "PRODUCE", "水果类", "4.20", "7.80", 61),
    ("P00018", "阳光玫瑰葡萄", "PRODUCE", "水果类", "22.00", "35.80", 16),
    ("P00019", "有机西兰花", "PRODUCE", "蔬菜类", "6.00", "10.80", 44),
    ("P00020", "北海道甜玉米", "PRODUCE", "蔬菜类", "5.00", "8.80", 53),
]


async def ensure_departments(db: AsyncSession) -> dict[str, Department]:
    """创建缺少的固定部门，并返回按代码索引的部门。"""

    departments: dict[str, Department] = {}
    for code, name, _regular_name, _contract_name in DEPARTMENT_DATA:
        department = await db.scalar(select(Department).where(Department.code == code))
        if department is None:
            department = Department(code=code, name=name, is_active=True)
            db.add(department)
            await db.flush()
        departments[code] = department
    return departments


async def ensure_employees(db: AsyncSession, departments: dict[str, Department]) -> None:
    """保证每个部门拥有一名正式员工和一名契约工。"""

    password_hash = hash_password(DEFAULT_PASSWORD)
    for code, _name, regular_name, contract_name in DEPARTMENT_DATA:
        department = departments[code]
        employee_specs = [
            (EmployeeRole.REGULAR_EMPLOYEE, regular_name),
            (EmployeeRole.CONTRACT_WORKER, contract_name),
        ]
        for role, employee_name in employee_specs:
            statement = select(Employee).where(
                Employee.department_id == department.id,
                Employee.role == role,
            )
            employee = await db.scalar(statement)
            if employee is None:
                await create_employee(
                    name=employee_name,
                    role=role,
                    department_id=department.id,
                    password_hash=password_hash,
                    db=db,
                )


async def ensure_categories(
    db: AsyncSession,
    departments: dict[str, Department],
) -> dict[tuple[str, str], Category]:
    """创建各部门缺少的商品分类。"""

    categories: dict[tuple[str, str], Category] = {}
    for code, names in CATEGORY_DATA.items():
        department = departments[code]
        for name in names:
            statement = select(Category).where(
                Category.department_id == department.id,
                Category.name == name,
            )
            category = await db.scalar(statement)
            if category is None:
                category = Category(
                    department_id=department.id,
                    name=name,
                    is_active=True,
                )
                db.add(category)
                await db.flush()
            categories[(code, name)] = category
    return categories


async def ensure_products(
    db: AsyncSession,
    departments: dict[str, Department],
    categories: dict[tuple[str, str], Category],
) -> list[Product]:
    """创建缺少的二十个演示商品。"""

    products: list[Product] = []
    for product_no, name, code, category_name, cost, price, stock in PRODUCT_DATA:
        product = await db.scalar(select(Product).where(Product.product_no == product_no))
        if product is None:
            product = Product(
                product_no=product_no,
                name=name,
                department_id=departments[code].id,
                category_id=categories[(code, category_name)].id,
                purchase_price=Decimal(cost),
                sale_price=Decimal(price),
                stock_quantity=stock,
                status=ProductStatus.ON_SALE,
            )
            db.add(product)
            await db.flush()
        products.append(product)
    return products


async def ensure_sales(db: AsyncSession, products: list[Product]) -> None:
    """销售表为空时生成最近七天的销售单和销售明细。"""

    existing_sale_count = await db.scalar(select(func.count(Sale.id)))
    if existing_sale_count:
        return

    randomizer = random.Random(RANDOM_SEED)
    today = datetime.now().date()
    sale_times = [time(9, 20), time(11, 5), time(13, 40), time(16, 10), time(18, 25), time(20, 15)]
    sequence = 1

    for days_ago in range(6, -1, -1):
        sale_date = today - timedelta(days=days_ago)
        for sale_time in sale_times:
            selected_products = randomizer.sample(products, randomizer.randint(2, 4))
            item_values: list[tuple[Product, int, Decimal, Decimal]] = []
            total_amount = Decimal("0.00")
            total_cost = Decimal("0.00")

            for product in selected_products:
                quantity = randomizer.randint(1, 4)
                subtotal = product.sale_price * quantity
                cost_subtotal = product.purchase_price * quantity
                item_values.append((product, quantity, subtotal, cost_subtotal))
                total_amount += subtotal
                total_cost += cost_subtotal

            sale = Sale(
                sale_no=f"S{sale_date:%Y%m%d}{sequence:04d}",
                sold_at=datetime.combine(sale_date, sale_time),
                total_amount=total_amount,
                total_cost=total_cost,
                gross_profit=total_amount - total_cost,
                source=SaleSource.DEMO_SEED,
            )
            db.add(sale)
            await db.flush()

            for product, quantity, subtotal, cost_subtotal in item_values:
                db.add(
                    SaleItem(
                        sale_id=sale.id,
                        product_id=product.id,
                        product_no_snapshot=product.product_no,
                        product_name_snapshot=product.name,
                        department_id=product.department_id,
                        quantity=quantity,
                        unit_price=product.sale_price,
                        unit_cost=product.purchase_price,
                        subtotal=subtotal,
                        cost_subtotal=cost_subtotal,
                    )
                )
            sequence += 1


async def print_summary(db: AsyncSession) -> None:
    """打印当前数据库中的主要演示数据数量。"""

    counts = [
        ("部门", await db.scalar(select(func.count(Department.id)))),
        ("员工", await db.scalar(select(func.count(Employee.id)))),
        ("分类", await db.scalar(select(func.count(Category.id)))),
        ("商品", await db.scalar(select(func.count(Product.id)))),
        ("销售单", await db.scalar(select(func.count(Sale.id)))),
        ("销售明细", await db.scalar(select(func.count(SaleItem.id)))),
    ]
    for label, count in counts:
        print(f"{label}：{count or 0}")

    employees = list((await db.scalars(select(Employee).order_by(Employee.id.asc()))).all())
    print("员工账号：")
    for employee in employees:
        print(f"  {employee.employee_no}  {employee.name}  {employee.role.value}")


async def validate_sales(db: AsyncSession) -> None:
    """确认每张销售单的汇总金额与销售明细完全一致。"""

    statement = select(Sale).options(selectinload(Sale.items))
    sales = list((await db.scalars(statement)).all())
    for sale in sales:
        total_amount = sum((item.subtotal for item in sale.items), Decimal("0.00"))
        total_cost = sum((item.cost_subtotal for item in sale.items), Decimal("0.00"))
        if sale.total_amount != total_amount:
            raise RuntimeError(f"销售单 {sale.sale_no} 的销售总金额与明细不一致")
        if sale.total_cost != total_cost:
            raise RuntimeError(f"销售单 {sale.sale_no} 的销售成本与明细不一致")
        if sale.gross_profit != total_amount - total_cost:
            raise RuntimeError(f"销售单 {sale.sale_no} 的毛利润计算不正确")


async def seed_demo_data() -> None:
    """在一个事务中补齐所有第一版演示数据。"""

    async with async_session_factory() as db:
        try:
            departments = await ensure_departments(db)
            await ensure_employees(db, departments)
            categories = await ensure_categories(db, departments)
            products = await ensure_products(db, departments, categories)
            await ensure_sales(db, products)
            await db.commit()
            await validate_sales(db)
            print("演示数据初始化完成")
            await print_summary(db)
            print(f"员工临时密码：{DEFAULT_PASSWORD}")
        except Exception:
            await db.rollback()
            raise


async def main() -> None:
    """执行演示数据初始化并释放数据库连接池。"""

    try:
        await seed_demo_data()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
