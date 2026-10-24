# 智匠 Web（Next.js + Ant Design）

一般无需单独启动，请在项目根目录运行：

```bash
# Windows
..\start.bat

# Linux / macOS
../start.sh
```

前端地址：http://127.0.0.1:3000  
管理页：http://127.0.0.1:3000/admin  

API 代理：`/api-proxy/*` → `API_ORIGIN`（启动脚本会写入 `.env.local`，默认 `http://127.0.0.1:8002`）。
