"""统一操作审计记录 ORM 模型。"""

from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class OperationAuditLog(CreatedAtMixin, Base):
    """保存重要修改操作的目标、修改前后数据、操作人及可选理由。"""

    __tablename__ = "operation_audit_log"
    __table_args__ = {"mysql_charset": "utf8mb4", "comment": "操作审计记录表"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="审计记录主键"
    )
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="操作员工ID",
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="业务模块")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作类型")
    target_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="目标类型"
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="目标记录ID"
    )
    before_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="修改前数据"
    )
    after_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="修改后数据"
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="修改理由")


__all__ = ["OperationAuditLog"]
