"""公司门店及各店启用的统一部门。"""
from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

# region 门店模型
class Store(TimestampMixin, Base):
    __tablename__ = "store"
    __table_args__ = (UniqueConstraint("store_no", name="uq_store_no"), {"mysql_charset": "utf8mb4", "comment": "门店表"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="门店ID")
    store_no: Mapped[str] = mapped_column(String(20), comment="门店编号")
    name: Mapped[str] = mapped_column(String(100), comment="门店名称")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="门店地址")
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="联系电话")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Tokyo", server_default="Asia/Tokyo", comment="门店时区")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"), comment="是否启用")
# endregion

# region 门店部门配置
class StoreDepartment(TimestampMixin, Base):
    __tablename__ = "store_department"
    __table_args__ = ({"mysql_charset": "utf8mb4", "comment": "门店部门启用配置表"},)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"), primary_key=True, comment="门店ID")
    department_id: Mapped[int] = mapped_column(ForeignKey("department.id"), primary_key=True, comment="统一部门ID")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"), comment="本店是否启用此部门")
# endregion
