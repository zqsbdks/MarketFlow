"""按员工与门店保存AI会话、摘要及完整消息。"""

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin


# region 会话
class AiConversation(TimestampMixin, Base):
    __tablename__ = "ai_conversation"
    __table_args__ = {"mysql_charset": "utf8mb4", "comment": "员工AI会话表"}
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="会话ID"
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id"), index=True, comment="所属账号ID"
    )
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id"), index=True, nullable=True, comment="会话业务门店"
    )
    home_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id"), nullable=True, comment="会话创建时员工归属门店；用于异动后访问检查"
    )
    title: Mapped[str] = mapped_column(String(100), comment="会话标题")
    provider: Mapped[str] = mapped_column(String(20), comment="模型供应商")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="模型名称")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="较早对话摘要")
    summary_through_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="摘要覆盖至消息ID"
    )


# endregion


# region 历史消息
class AiMessage(CreatedAtMixin, Base):
    __tablename__ = "ai_message"
    __table_args__ = {"mysql_charset": "utf8mb4", "comment": "AI完整历史消息表"}
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="消息ID"
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversation.id", ondelete="CASCADE"), index=True, comment="所属会话ID"
    )
    role: Mapped[str] = mapped_column(String(20), comment="user/model/tool")
    content: Mapped[str] = mapped_column(Text, comment="消息或工具结果正文")
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="待确认操作引用")


# endregion
