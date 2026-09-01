# Windows 兼容入口；完整逻辑统一由跨平台 Python 脚本维护。
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
& python (Join-Path $projectRoot "scripts\setup.py")
exit $LASTEXITCODE
