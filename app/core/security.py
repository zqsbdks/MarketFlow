"""密码安全模块。

本模块封装了密码哈希与密码验证逻辑，确保用户密码在数据库中以不可逆方式存储，
同时在登录时能正确校验明文密码与哈希结果是否匹配。
"""

from passlib.context import CryptContext

# Argon2 上下文可在整个进程内复用，无需为每次请求重复创建。
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """生成密码的哈希值。

    Args:
        password (str): 明文密码。

    Returns:
        str: 加密后的密码哈希值。
    """

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希密码是否匹配。

    Args:
        plain_password (str): 用户输入的明文密码。
        hashed_password (str): 数据库中保存的哈希密码。

    Returns:
        bool: 若匹配则返回 True，否则返回 False。
    """

    return pwd_context.verify(plain_password, hashed_password)
