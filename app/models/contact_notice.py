"""联络事项和发布时固定的员工接收记录。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, TimestampMixin


# region 联络事项主表
class ContactNotice(TimestampMixin, Base):
    """保存正文、接收范围和关闭条件；关闭后保留历史。"""

    __tablename__ = "contact_notice"
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id"), nullable=True, index=True, comment="发布门店；总部为空"
    )
    source: Mapped[str] = mapped_column(
        String(20), default="store", server_default="store", comment="发布来源：门店或总部"
    )
    target_store_ids: Mapped[list[int] | None] = mapped_column(
        JSON, nullable=True, comment="总部指定门店；空列表表示全部门店"
    )
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('all', 'department', 'personal')", name="ck_notice_target"
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'closed', 'withdrawn')", name="ck_notice_status"
        ),
        CheckConstraint("priority IN ('normal', 'important', 'urgent')", name="ck_notice_priority"),
        {"mysql_charset": "utf8mb4", "comment": "联络事项表"},
    )
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="联络事项ID"
    )
    title: Mapped[str] = mapped_column(String(100), comment="标题")
    content: Mapped[str] = mapped_column(Text, comment="正文")
    priority: Mapped[str] = mapped_column(
        String(20), default="normal", comment="优先级：普通、重要、紧急"
    )
    target_type: Mapped[str] = mapped_column(String(20), comment="接收范围：全体、部门、个人")
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("department.id"), nullable=True, comment="接收部门ID"
    )
    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id"), index=True, comment="发布员工ID"
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime, comment="开始展示时间")
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="确认截止时间"
    )
    close_on_all_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), comment="全员确认后自动关闭"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft", index=True, comment="草稿、已发布、已关闭、已撤回"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="关闭时间")
    close_reason: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="关闭原因")
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), comment="乐观锁版本号"
    )


# endregion


# region 员工接收记录
class ContactNoticeRecipient(CreatedAtMixin, Base):
    """发布时生成名单，查看与确认不会改变接收范围。"""

    __tablename__ = "contact_notice_recipient"
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id"), nullable=True, index=True, comment="发布时接收员工所属门店快照"
    )
    __table_args__ = (
        UniqueConstraint("notice_id", "employee_id", name="uq_notice_recipient"),
        {"mysql_charset": "utf8mb4", "comment": "联络事项员工确认表"},
    )
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="接收记录ID"
    )
    notice_id: Mapped[int] = mapped_column(
        ForeignKey("contact_notice.id", ondelete="CASCADE"), index=True, comment="联络事项ID"
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employee.id"), index=True, comment="接收员工ID"
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="首次查看时间"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="确认时间"
    )


# endregion
