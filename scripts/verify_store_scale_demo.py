"""Read-only verification and per-store report for the scaled supermarket demo."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.core.business_time import business_now
from app.core.database import async_engine, async_session_factory
from app.models.contact_notice import ContactNotice
from app.models.discount_rule import DiscountRule
from app.models.employee import Employee
from app.models.inventory_batch import InventoryBatch
from app.models.operation_audit_log import OperationAuditLog
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from scripts.seed_store_scale_demo import MARKER, validate_store


async def main():
    now = business_now().replace(microsecond=0)
    report = {"verified_at_japan": now.isoformat(), "stores": []}
    try:
        async with async_session_factory() as db:
            stores = (await db.scalars(select(Store).order_by(Store.id))).all()
            counts = {}
            for model in (
                Product,
                Supplier,
                SupplierProduct,
                Employee,
                Purchase,
                InventoryBatch,
                Sale,
                DiscountRule,
                ContactNotice,
                OperationAuditLog,
            ):
                counts[model.__tablename__] = dict(
                    (
                        await db.execute(
                            select(model.store_id, func.count()).group_by(model.store_id)
                        )
                    ).all()
                )
            recent = dict(
                (
                    await db.execute(
                        select(Sale.store_id, func.count())
                        .where(Sale.sold_at >= now - timedelta(days=7))
                        .group_by(Sale.store_id)
                    )
                ).all()
            )
            amounts = {
                sid: {
                    "revenue": str(revenue),
                    "cost": str(cost),
                    "gross_profit": str(profit),
                    "first_sale": first.isoformat(),
                    "last_sale": last.isoformat(),
                }
                for sid, revenue, cost, profit, first, last in (
                    await db.execute(
                        select(
                            Sale.store_id,
                            func.sum(Sale.total_amount),
                            func.sum(Sale.total_cost),
                            func.sum(Sale.gross_profit),
                            func.min(Sale.sold_at),
                            func.max(Sale.sold_at),
                        ).group_by(Sale.store_id)
                    )
                ).all()
            }
            completed = set(
                (
                    await db.scalars(
                        select(OperationAuditLog.store_id).where(OperationAuditLog.action == MARKER)
                    )
                ).all()
            )
            for store in stores:
                row = {
                    "store_no": store.store_no,
                    "name": store.name,
                    "id": store.id,
                    "counts": {name: values.get(store.id, 0) for name, values in counts.items()},
                    "last_7_days_sales": recent.get(store.id, 0),
                    "sales": amounts.get(store.id),
                }
                if store.id > 1:
                    if store.id not in completed:
                        raise RuntimeError(f"Store {store.id} missing completion marker")
                    row["validation"] = await validate_store(db, store.id)
                    if row["counts"]["product"] != 40 or row["counts"]["sale"] < 14000:
                        raise RuntimeError(f"Store {store.id} has insufficient demo volume")
                    if not row["last_7_days_sales"]:
                        raise RuntimeError(f"Store {store.id} has no recent sales")
                report["stores"].append(row)
                print(
                    f"{store.store_no}: {row['counts']['sale']} sales, "
                    f"{row['counts']['purchase']} purchases, verified",
                    flush=True,
                )
        folder = Path(__file__).resolve().parents[1] / "docs" / "verification"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "store-data-summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        lines = [
            "# 多店演示数据验收",
            "",
            f"验收时间（日本）：{now.isoformat()}",
            "",
            "DP0001 保持原有业务数据，其余 29 家追加约半年随机业务数据。",
            "每家新增店均验证销售与采购金额、到货/销售/保质期关系、门店归属、",
            "批次初始数量 = 销售数量 + 废弃数量 + 剩余数量，以及商品总库存一致性。",
            "",
            "各店有独立随机种子、商品偏好、价格差异、周末客流和晚间折扣。",
            "历史过期余货有废弃流水，近期过期余货保留供清理演示。",
            "",
            "| 门店 | 商品 | 采购单 | 库存批次 | 销售单 | 近7天销售单 | 折扣 | 店内联络 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in report["stores"]:
            c = row["counts"]
            lines.append(
                f"| {row['store_no']} {row['name']} | {c['product']} | {c['purchase']} | "
                f"{c['inventory_batch']} | {c['sale']} | {row['last_7_days_sales']} | "
                f"{c['discount_rule']} | {c['contact_notice']} |"
            )
        lines.extend(
            [
                "",
                "生成：`python -m scripts.seed_store_scale_demo --workers 3`",
                "",
                "复核：`python -m scripts.verify_store_scale_demo`",
                "",
                "生成脚本按店独立事务，失败店回滚；已完成店通过标记跳过。",
                "账号密码不写入本报告。",
                "",
            ]
        )
        (folder / "STORE_DATA_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
