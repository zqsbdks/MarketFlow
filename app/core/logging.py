"""应用与第三方库的集中日志配置。"""

from logging.config import dictConfig
from pathlib import Path

from app.core.config import settings


def configure_logging() -> None:
    """配置控制台日志，以及可选的轮转文件日志。

    文件达到 10 MB 后自动轮转，最多保留 5 份历史文件。重复调用会重新应用
    ``dictConfig``，这使测试创建多个应用实例时仍能得到一致配置。
    """

    # 控制台处理器始终启用，适合本地开发和容器日志采集。
    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        }
    }

    if settings.log_file:
        # 仅在显式配置文件路径时创建目录，默认运行不会产生额外文件。
        log_path = Path(settings.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": str(log_path),
            "maxBytes": 10 * 1024 * 1024,  # 单个日志文件最大 10 MB。
            "backupCount": 5,  # 保留最近 5 个备份文件。
            "encoding": "utf-8",
        }

    # disable_existing_loggers=False 保留 Uvicorn、SQLAlchemy 等库的日志器。
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": handlers,
            "root": {
                "level": settings.log_level.upper(),
                "handlers": list(handlers),
            },
        }
    )
