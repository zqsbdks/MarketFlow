"""异常数量检查与绑定具体操作的短期确认凭据。"""

import hashlib
import hmac
import json
import time

from app.core.config import settings


def quantity_reasons(quantity: int, reference: int, previous: int) -> list[str]:
    """返回人工输入的疑似误按或超量原因；不修改任何状态。

    reference是业务参考量，previous是已保存量。0或未改变的量不重复提醒。
    至少50且达到参考量5倍、原量乘10、两位以上相同数字分别产生独立原因。
    输入来源筛选由check_confirmation负责，自动计算不走这套误按规则。"""
    if quantity <= 0 or quantity == previous:
        return []
    reasons = []
    if quantity >= 50 and quantity >= max(50, reference * 5):
        reasons.append("far_above_reference")
    if previous > 0 and quantity == previous * 10:
        reasons.append("possible_extra_zero")
    if quantity >= 11 and len(set(str(quantity))) == 1:
        reasons.append("possible_repeated_key")
    return reasons


def check_confirmation(request, actor_id, store_id, kind, reference, previous) -> dict | None:
    """返回None、已确认审计数据，或带saved=false的确认挑战。

    加减键只保留明显超量提醒，键盘/粘贴保留重复数字和多输入0提醒。
    HMAC签名覆盖员工、店铺、部门、商品、到货日、数量及操作类型，有效10分钟。
    动态参考量不进签名，避免库存变化导致相同已确认数字反复弹窗。
    这里只检查签名，不提交数据库；调用方还必须校验权限、截止时间并记录审计。"""
    quantity = request.quantity if kind == "order" else request.minimum_stock
    if quantity is None:
        return None
    reasons = quantity_reasons(quantity, reference, previous)
    if request.input_method == "stepper":
        reasons = [reason for reason in reasons if reason == "far_above_reference"]
    if not reasons:
        return None
    # 凭据不绑定动态建议量，避免正常库存变化让已确认的相同数量反复弹窗。
    binding = json.dumps(
        {
            "actor": actor_id,
            "store": store_id,
            "kind": kind,
            "department": request.department_id,
            "product": request.supplier_product_id,
            "date": str(getattr(request, "arrival_date", "")),
            "quantity": quantity,
        },
        sort_keys=True,
    )

    def signature(expires: str) -> str:
        return hmac.new(
            settings.secret_key.encode(),
            f"quantity-confirmation:{binding}:{expires}".encode(),
            hashlib.sha256,
        ).hexdigest()

    token = request.confirmation_token or ""
    expires, _, digest = token.partition(".")
    if (
        expires.isdigit()
        and int(expires) >= time.time()
        and hmac.compare_digest(digest, signature(expires))
    ):
        return {"confirmed": True, "reasons": reasons, "reference": reference}
    expires = str(int(time.time()) + 600)
    return {
        "confirmation_required": True,
        "saved": False,
        "confirmation_token": f"{expires}.{signature(expires)}",
        "quantity": quantity,
        "reference": reference,
        "previous": previous,
        "reasons": reasons,
    }
