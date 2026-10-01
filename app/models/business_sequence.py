"""并发安全的业务编号计数器 ORM 模型。"""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BusinessSequence(TimestampMixin, Base):
    """保存不同业务、不同日期的最后已分配流水号。"""

    __tablename__ = "business_sequence"
    __table_args__ = ({"mysql_charset": "utf8mb4", "comment": "业务编号计数器表"},)

    sequence_key: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="计数器键，例如sale:20261001"
    )
    current_value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="最后已分配的流水号"
    )


__all__ = ["BusinessSequence"]
