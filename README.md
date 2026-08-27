# 企知 · 企业内部知识问答智能体

基于 **智匠・工业大模型** 与 **RAG（检索增强生成）** 技术，为荣成康派斯新能源车辆股份有限公司（康派斯）员工定制的企业内部知识问答系统。支持上传制度文档（PDF / Word / Markdown），通过向量检索 + LangChain Agent 为员工解答操作规范、管理制度、流程制度等问题，并在回答中标注文档来源。

> 当前版本为 **V1**：全员共用同一知识库，暂不做权限隔离与多租户。

---

## 功能概览


| 模块             | 说明                             |
| -------------- | ------------------------------ |
| 员工问答 `/`       | 多轮对话、历史会话、基于知识库检索作答            |
| 知识库管理 `/admin` | 文档上传、重建索引、原文预览、切片预览、删除文档       |
| 后端 API         | FastAPI，提供问答、会话、文档管理接口         |
| 向量检索           | Chroma + BGE 中文 Embedding（CPU） |
| 大模型            | 对接内网 OpenAI 兼容 vLLM 服务         |


---

## 技术栈


| 层级    | 技术                                      |
| ----- | --------------------------------------- |
| 大模型   | vLLM（OpenAI 兼容 API），默认 Qwen3.5-VL-122B  |
| Agent | LangChain Agent + LangGraph SqliteSaver |
| RAG   | LangChain Chroma、BAAI/bge-small-zh-v1.5 |
| 后端    | Python 3.11+、FastAPI、Uvicorn            |
| 前端    | Next.js 15、TypeScript、Ant Design 6      |
| 存储    | 原始文档（文件系统）、向量库（Chroma）、会话（SQLite）       |


---



## 系统架构

```
上传文档 → data/raw/（原始文件）
    ↓ 重建索引
解析 / 分块 → Embedding → Chroma 向量库
    ↓
员工提问 → Agent 调用 search_knowledge / list_documents
    ↓
内网 LLM 生成回答（附来源文件名）
```

**数据存储说明：**


| 路径                    | 内容                           |
| --------------------- | ---------------------------- |
| `data/raw/`           | 原始 PDF / Word / Markdown 文件  |
| `data/chroma/`        | 文档切片向量与元数据（Chroma）           |
| `data/db/kb_agent.db` | 会话列表与 LangGraph 对话状态（SQLite） |


---



## 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 18（推荐 20+，用于 Next.js 前端）
- **npm** 或 **pnpm**
- 可访问的内网 **vLLM** 服务（需 VPN 时使用）
- **Embedding 模型权重**（约 90MB，默认不随 Git 提交，需自行准备）

---



## 配置与安装



### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd enterprise_kb_agent
```



### 2. 创建 Python 虚拟环境并安装后端依赖

在项目目录或上级目录创建虚拟环境均可（启动脚本会自动查找 `../.venv` 或 `.venv`）：

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\pip install -e .

# Linux / macOS
python3 -m venv .venv
.venv/bin/pip install -e .
```



### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，按实际环境修改：

```ini
# 内网 vLLM（需先连 VPN）
VLLM_BASE_URL=http://10.60.40.130:12333/v1
VLLM_API_KEY=EMPTY
VLLM_MODEL=Qwen3.5-VL-122B
VLLM_ENABLE_THINKING=false

# 本地 Embedding 模型目录（相对项目根）
EMBEDDING_MODEL_PATH=models/bge-small-zh-v1.5

# 检索与分块（可选）
RETRIEVE_TOP_K=4
CHUNK_SIZE=700
CHUNK_OVERLAP=100
LOG_LEVEL=INFO
```

验证模型服务是否可用：

```bash
curl http://10.60.40.130:12333/v1/models
```



### 4. 准备 Embedding 模型

权重默认不在 Git 仓库中，请将 `bge-small-zh-v1.5` 放到 `models/bge-small-zh-v1.5/`，详见 [models/README.md](./models/README.md)。

目录中应包含 `config.json`、`model.safetensors`、`tokenizer.json` 等文件。

### 5. 安装前端依赖

```bash
cd web
npm install
cd ..
```

> 使用一键启动脚本时，若 `web/node_modules` 不存在会自动执行 `npm install`。  
> 前端代理地址 `web/.env.local` 也会由启动脚本自动生成，默认指向 `http://127.0.0.1:8002`。

---



## 启动命令



### 一键启动（推荐）

前后端在同一终端运行，`Ctrl+C` 会同时停止并释放端口。

**Windows（PowerShell / CMD）：**

```bash
.\start.bat
# 或
.\start.ps1
```

**Linux / macOS：**

```bash
chmod +x start.sh
./start.sh
```

**自定义端口（Linux / macOS）：**

```bash
API_PORT=8002 WEB_PORT=3000 ./start.sh
```

**Windows 自定义端口：**

```powershell
.\start.ps1 -ApiPort 8002 -WebPort 3000
```

启动成功后访问：


| 入口     | 地址                                                           |
| ------ | ------------------------------------------------------------ |
| 员工问答   | [http://127.0.0.1:3000](http://127.0.0.1:3000)               |
| 知识库管理  | [http://127.0.0.1:3000/admin](http://127.0.0.1:3000/admin)   |
| API 文档 | [http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs)     |
| 健康检查   | [http://127.0.0.1:8002/health](http://127.0.0.1:8002/health) |


默认端口：**API** `8002`，**Web** `3000`。

### 手动分别启动（开发调试）

**终端 1 — 后端：**

```bash
# Windows
.\.venv\Scripts\python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload --reload-dir src

# Linux / macOS
.venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload --reload-dir src
```

**终端 2 — 前端：**

```bash
cd web
echo API_ORIGIN=http://127.0.0.1:8002 > .env.local
npm run dev -- --port 3000 --hostname 127.0.0.1
```

---



## 使用说明



### 知识库入库流程

1. 打开 **知识库管理** 页 `/admin`
2. **上传文档** → 文件保存到 `data/raw/`（此时不会自动向量化）
3. 点击 **重建索引** → 解析、分块、Embedding、写入 Chroma
4. 在问答页提问，Agent 通过向量检索回答并标注来源



### 命令行批量入库

```bash
# 入库 data/raw/ 下全部支持的文件
python scripts/ingest_folder.py

# 入库 samples/ 下的示例制度文档
python scripts/ingest_folder.py --samples
```



### 支持的文档格式

- PDF（需可复制文本，暂不支持扫描版 OCR）
- Word（`.docx`）
- Markdown（`.md`）

---



## 主要 API


| 方法                  | 路径                                       | 说明             |
| ------------------- | ---------------------------------------- | -------------- |
| GET                 | `/health`                                | 健康检查           |
| GET / POST / DELETE | `/api/v1/threads`                        | 会话列表 / 创建 / 删除 |
| GET                 | `/api/v1/threads/{id}/messages`          | 会话消息历史         |
| POST                | `/api/v1/chat`                           | 知识问答           |
| GET                 | `/api/v1/admin/documents`                | 文档列表           |
| POST                | `/api/v1/admin/upload`                   | 上传原始文档         |
| POST                | `/api/v1/admin/ingest`                   | 重建向量索引         |
| GET                 | `/api/v1/admin/documents/{file}/preview` | 原文预览           |
| GET                 | `/api/v1/admin/documents/{file}/chunks`  | 切片预览           |
| DELETE              | `/api/v1/admin/documents/{file}`         | 删除原文与向量        |


---



## 项目结构

```
enterprise_kb_agent/
├── start.bat / start.ps1 / start.sh   # 一键启动
├── .env.example                       # 环境变量模板
├── pyproject.toml                     # Python 依赖
├── README.md
├── samples/                           # 示例制度 Markdown
├── scripts/
│   └── ingest_folder.py               # 命令行批量入库
├── models/
│   └── README.md                      # Embedding 模型说明
├── data/
│   ├── raw/                           # 原始上传文档
│   ├── chroma/                        # 向量库（运行时生成）
│   ├── db/                            # 会话 SQLite（运行时生成）
│   └── logs/                          # 应用日志
├── src/
│   ├── config.py                      # 配置项
│   ├── llm.py                         # vLLM 客户端
│   ├── ingest/                        # 文档解析与入库
│   ├── rag/                           # Embedding 与 Chroma
│   ├── agent/                         # Agent 与工具
│   ├── api/                           # FastAPI 路由
│   └── sessions/                      # 会话元数据
├── web/                               # Next.js 前端
└── docs/
    └── 项目技术分析.md                 # 详细技术文档
```

---



## 日志


| 位置                                      | 说明                        |
| --------------------------------------- | ------------------------- |
| `data/logs/app.log`                     | 常规运行日志                    |
| `data/logs/error.log`                   | ERROR 级别日志                |
| `data/api.out.log` / `data/api.err.log` | 启动脚本捕获的 API 标准输出（Windows） |
| `data/api.log`                          | Linux / macOS 下 API 日志    |


日志级别可通过 `.env` 中的 `LOG_LEVEL` 调整。

---



## 部署注意事项

1. **vLLM 工具调用**：服务端需开启
  `--enable-auto-tool-choice --tool-call-parser qwen3_xml`（或对应 Qwen 解析器），否则 Agent 无法调用检索工具。
2. **Embedding 离线部署**：确保 `models/bge-small-zh-v1.5` 目录完整，或将 `EMBEDDING_MODEL_PATH` 改为本地绝对路径。
3. **敏感文件勿提交 Git**：`.env`、`data/` 运行数据、`web/.env.local`、`web/node_modules` 等已在 `.gitignore` 中排除。
4. **热重载**：修改 `src/` 下 Python 代码会触发 API 自动重启；修改期间前端可能出现短暂的 `ECONNRESET` 代理错误，刷新即可。
5. **PDF 限制**：V1 不支持扫描版 PDF；部分国标 PDF 可能出现乱码，需换用文本质量更好的版本或后续接入 OCR。

