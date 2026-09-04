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
