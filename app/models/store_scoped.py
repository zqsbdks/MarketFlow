"""门店业务数据共用的所属门店字段。"""
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class StoreScopedMixin:
    """请求内自动填写门店，后台任务显式传入业务来源门店。"""
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"), index=True, nullable=False, default=1, comment="所属门店ID")
