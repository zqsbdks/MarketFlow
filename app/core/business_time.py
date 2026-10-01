"""统一日本门店业务时间；数据库现有 DATETIME 字段按日本本地时间保存。"""

from datetime import datetime
from zoneinfo import ZoneInfo

BUSINESS_TIME_ZONE = ZoneInfo("Asia/Tokyo")


def business_now() -> datetime:
    """返回与现有无时区数据库字段兼容的日本本地时间。"""

    return datetime.now(BUSINESS_TIME_ZONE).replace(tzinfo=None)


__all__ = ["BUSINESS_TIME_ZONE", "business_now"]
