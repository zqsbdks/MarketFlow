"""FastAPI 应用顶层 Python 包。

此处故意保持无副作用：导入 ``app`` 不会创建连接或启动服务。ASGI 对象位于
``app.main``，由 Uvicorn 在需要时显式加载。
"""
