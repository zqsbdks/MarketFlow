"""异常数量检查与绑定具体操作的短期确认凭据。"""

import hashlib
import hmac
import json
import time

from app.core.config import settings


def quantity_reasons(quantity: int, reference: int, previous: int) -> list[str]:
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
