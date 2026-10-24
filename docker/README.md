# Docker 离线部署说明

本项目提供**单镜像**部署：容器内同时运行 FastAPI（`:8002`）与 Next.js（`:3000`）。  
大模型使用内网 vLLM（通过环境变量配置），**不**打进镜像。Embedding 模型 `bge-small-zh-v1.5` 会打进镜像。

## 前置条件

### 构建机（需能访问镜像源 / PyPI / npm）

- Docker Engine 或 Docker Desktop
- 完整 Embedding 权重：`models/bge-small-zh-v1.5/`（含 `model.safetensors`）

### 无网服务器

- 已安装 Docker（可用内网安装包离线安装）
- 能访问内网 vLLM：`curl http://<vLLM地址>/v1/models`

---

## 一、有网机构建并导出

在项目根目录：

```bash
# Linux / macOS
chmod +x scripts/docker-export.sh scripts/docker-import.sh docker/entrypoint.sh
./scripts/docker-export.sh
```

```powershell
# Windows PowerShell
.\scripts\docker-export.ps1
```

产物在 `dist/`：

| 文件 | 说明 |
|------|------|
| `enterprise-kb-agent-1.0.tar` | 镜像包（体积较大，含 torch + 模型） |
| `docker-compose.yml` | 启动编排 |
| `.env.example` | 环境变量模板 |
| `docker-import.sh` / `.ps1` | 无网机导入脚本 |

将整个 `dist/` 目录拷到 U 盘 / 内网文件服务器即可。

也可手动：

```bash
docker build -t enterprise-kb-agent:1.0 .
docker save enterprise-kb-agent:1.0 -o enterprise-kb-agent-1.0.tar
```

---

## 二、无网服务器导入并启动

```bash
cd dist   # 或你放置 tar 的目录
cp .env.example .env
# 编辑 .env：至少改 VLLM_BASE_URL、VLLM_MODEL、JWT_SECRET、管理员密码

chmod +x docker-import.sh
./docker-import.sh
```

Windows：

```powershell
Copy-Item .env.example .env
# 编辑 .env 后
.\docker-import.ps1
```

访问：

- 问答：`http://<服务器IP>:3000`
- 管理：`http://<服务器IP>:3000/admin`
- API 文档：`http://<服务器IP>:8002/docs`

数据（文档、向量库、会话）保存在 Docker volume `kb_data`，升级镜像不会丢。

---

## 三、常用运维命令

```bash
docker compose logs -f          # 日志
docker compose restart          # 重启
docker compose down             # 停止（不删 volume）
docker compose down -v          # 停止并删除数据卷（危险）
```

更换新版本镜像：

```bash
docker load -i enterprise-kb-agent-1.0.tar
docker compose up -d
```

---

## 四、内网 LLM 连不通时

容器默认使用桥接网络。若访问不了宿主机所在内网的 vLLM：

1. 确认 `.env` 里 `VLLM_BASE_URL` 是**容器内可达**地址（不要用仅本机回环且未做映射的地址）。
2. Linux 可在 `docker-compose.yml` 中启用：
   ```yaml
   network_mode: host
   ```
   （启用后端口映射配置会被忽略，直接使用宿主机 3000/8002。）
3. 从容器内测试：
   ```bash
   docker exec -it enterprise-kb-agent wget -q -O - http://<vLLM>/v1/models
   ```

---

## 五、改源码后如何更新

1. 在有网机构建新镜像并 `docker save`
2. 拷到服务器 `docker load`
3. `docker compose up -d`（`data` volume 保留）

生产环境不要挂载源码热更新；开发请继续用本机 `./start.sh`。
