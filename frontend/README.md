# MarketFlow 前端

Vue 3 + TypeScript + Vite 编写的门店经营管理界面。

## 本地启动

先在项目根目录启动 FastAPI 后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

再打开另一个终端启动前端：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

浏览器访问 `http://127.0.0.1:5173`。开发服务器会把 `/api` 请求代理到
`http://127.0.0.1:8000`。

## 检查与构建

```powershell
npm.cmd run type-check
npm.cmd run build
```

如需连接其他后端地址，请复制 `.env.example` 为 `.env`，并修改
`VITE_API_BASE_URL`。

容器部署见项目根目录 [README](../README.md)。前端与 API 通过同一域名的
`/api/v1` 通信；生产环境必须使用 HTTPS，以便安全登录 Cookie 正常工作。
AI Key 在后端按员工加密保存，升级旧版本后需要重新输入一次。
登录页和主界面提供日语、英语、中文及日夜模式切换；语言默认日语，主题默认夜间，
两项选择都保存在当前浏览器中。
