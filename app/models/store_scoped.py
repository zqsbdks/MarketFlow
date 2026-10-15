"""门店业务数据共用的所属门店字段。"""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class StoreScopedMixin:
    """只定义所属门店字段；CRUD 明确填写门店，查询时明确添加门店条件。"""

    store_id: Mapped[int] = mapped_column(
        ForeignKey("store.id"), index=True, nullable=False, default=1, comment="所属门店ID"
    )
