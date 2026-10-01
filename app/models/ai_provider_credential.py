"""员工自己的模型供应商 API Key，仅保存加密密文。"""

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AiProviderCredential(TimestampMixin, Base):
    """每名员工对每个模型供应商最多保存一把密钥。"""

    __tablename__ = "ai_provider_credential"
    __table_args__ = (
        UniqueConstraint("employee_id", "provider", name="uq_ai_provider_credential_owner"),
        {"mysql_charset": "utf8mb4", "comment": "员工AI模型密钥表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="密钥记录ID"
    )
    employee_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("employee.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属员工ID",
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False, comment="模型供应商")
    encrypted_key: Mapped[str] = mapped_column(
        String(2048), nullable=False, comment="加密后的API密钥"
    )


__all__ = ["AiProviderCredential"]
