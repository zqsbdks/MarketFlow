"""AI 助手待确认操作 ORM 模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AiPendingAction(TimestampMixin, Base):
    """保存 AI 提议但尚未由当前员工确认执行的数据修改。"""

    __tablename__ = "ai_pending_action"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'executed', 'cancelled', 'expired', 'failed')",
            name="ck_ai_pending_action_status",
        ),
        {"mysql_charset": "utf8mb4", "comment": "AI待确认操作表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="待确认操作主键",
    )
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="发起操作的员工ID",
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="提出操作的模型供应商",
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="后端白名单操作类型",
    )
    arguments: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="经过校验的操作参数",
    )
    summary: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="向用户展示的修改预览",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="确认操作状态",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="确认截止时间",
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="实际执行完成时间",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="执行失败原因",
    )


__all__ = ["AiPendingAction"]
