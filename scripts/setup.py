"""跨平台项目初始化脚本，由系统 Python 直接运行。"""

from __future__ import annotations

import re
import secrets
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_FILE = PROJECT_ROOT / ".env"
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
DEV_REQUIREMENTS = PROJECT_ROOT / "requirements-dev.txt"
DEFAULT_SECRET = "dev-only-change-me-before-production"
MINIMUM_PYTHON = (3, 11)


def run(*args: str) -> None:
    """运行必须成功的子命令，失败时保留原始退出码和输出。"""

    subprocess.run(args, cwd=PROJECT_ROOT, check=True)


def create_environment_file() -> None:
    """按示例创建 .env，并只替换仍为默认值的开发密钥。"""

    if not ENV_EXAMPLE.is_file():
        raise FileNotFoundError(f"缺少环境变量示例文件：{ENV_EXAMPLE}")

    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("[OK] 已从 .env.example 创建 .env")
    else:
        print("[SKIP] .env 已存在，不会覆盖现有配置")

    content = ENV_FILE.read_text(encoding="utf-8")
    pattern = rf"(?m)^APP_SECRET_KEY=[\"']?{re.escape(DEFAULT_SECRET)}[\"']?\s*$"
    replacement = f'APP_SECRET_KEY="{secrets.token_urlsafe(64)}"'
    updated, count = re.subn(pattern, replacement, content)
    if count:
        ENV_FILE.write_text(updated, encoding="utf-8")
        print("[OK] 已生成随机 APP_SECRET_KEY")
    else:
        print("[SKIP] APP_SECRET_KEY 已配置")


def create_virtual_environment() -> None:
    """使用启动本脚本的 Python 创建项目虚拟环境。"""

    if VENV_PYTHON.is_file():
        print("[SKIP] .venv 已存在")
        return

    print(f"[RUN] 使用 {sys.executable} 创建 .venv")
    run(sys.executable, "-m", "venv", str(VENV_DIR))


def install_dependencies() -> None:
    """安装开发依赖并检查依赖冲突。"""

    print("[RUN] 升级 pip")
    run(str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip")
    print("[RUN] 安装运行与开发依赖")
    run(str(VENV_PYTHON), "-m", "pip", "install", "-r", str(DEV_REQUIREMENTS))
    run(str(VENV_PYTHON), "-m", "pip", "check")


def check_database_non_fatal() -> None:
    """检查数据库配置；数据库尚未创建时给出提示但不破坏初始化。"""

    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "scripts.check_database"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode:
        print("[WARN] 项目依赖已安装，但数据库尚不可用；修改 .env 后重新运行数据库检查任务")


def main() -> None:
    """执行可重复运行的完整初始化流程。"""

    if sys.version_info < MINIMUM_PYTHON:
        version = ".".join(map(str, MINIMUM_PYTHON))
        raise RuntimeError(f"本模板要求 Python {version} 或更高版本")
    create_environment_file()
    create_virtual_environment()
    install_dependencies()
    check_database_non_fatal()
    print("\n项目初始化完成。VS Code 任务会固定使用项目内的 .venv。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"\n[ERROR] 初始化失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
