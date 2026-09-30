# TravelAI（旅行智脑）

> 基于 **LLM 工具调用（Function Calling）· Agent · LangGraph · LangChain** 的智能旅行规划系统

用户用自然语言描述旅行需求，大模型自主决定调用哪些工具、调用几轮，最终生成一份可直接使用的完整行程攻略。

## 核心特性

- **自主工具调用** — 模型自行决策工具选择与调用轮次（ReAct 循环），而非固定流程
- **行程规划** — 根据目的地、天数、人数、预算生成逐日行程
- **实时数据** — 天气与路线走高德地图，景点 / 必玩地点 / 酒店走博查 AI 搜索（联网检索）
- **行程落地** — 支持导出 PDF、一键保存到「我的行程」
- **会话管理** — 历史咨询落库并可在左侧切换，会话栏可收缩
- **网页端配置** — 在页面上填写并测试各组 API Key，保存即生效，无需重启

## 技术栈

| 技术 | 用途 | 版本 |
| --- | --- | --- |
| Python | 后端核心语言 | 3.11 / 3.12 |
| FastAPI | API 框架 | 0.109+ |
| LangGraph / LangChain | Agent 工作流编排与工具集成 | 0.0.40+ / 0.1.20+ |
| SQLAlchemy 2.0 | ORM 数据库访问 | 2.0+ |
| SQLite / PostgreSQL | 主数据库 | SQLite / PG 15+ |
| 高德地图 Web 服务 | 天气查询 / 路线规划 | — |
| 博查 AI 搜索 | 景点 / 必玩地点 / 酒店检索 | — |
| Vue 3 + TypeScript | 前端框架 | 3.4+ / 5.3+ |
| Pinia | 状态管理 | 2.1+ |
| TailwindCSS + Arco Design Vue | 样式与 UI 组件 | 3.4+ / 2.6+ |
| Vite | 前端构建 | 5.0+ |
| ECharts | 地图可视化 | 5.5+ |
| ReportLab | 行程 PDF 生成 | 5.0+ |

## 项目结构

```
travel-agent1/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口（含启动配置自检）
│   │   ├── config.py            # 配置定义（.env）
│   │   ├── runtime_config.py    # 网页端配置覆盖（热生效）
│   │   ├── database.py
│   │   ├── models/              # SQLAlchemy 模型：user / trip / booking
│   │   ├── schemas/             # Pydantic 模型：user / trip / agent
│   │   ├── api/                 # API 路由：auth / trips / agent / settings
│   │   ├── agent/
│   │   │   ├── state.py  nodes.py  graph.py  memory.py
│   │   │   └── tools/
│   │   │       ├── weather_tools.py  spot_tools.py
│   │   │       ├── route_tools.py   booking_tools.py
│   │   │       └── amap_client.py   bocha_client.py
│   │   │           collector.py     errors.py
│   │   ├── assets/fonts/        # NotoSansSC Regular/Bold（PDF 用，SIL OFL）
│   │   ├── llm/client.py        # LLM 客户端（供应商可切换）
│   │   ├── services/            # trip_service / plan_extract / pdf_service
│   │   └── utils/               # helpers / auth
│   ├── tests/                   # 单元测试（全离线）
│   ├── scripts/                 # init_db / e2e_check / e2e_agent
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── api/                 # index / auth / trips / agent / settings
│   │   ├── components/          # common / trip / map
│   │   ├── views/               # Home / AIChat / TripCreate / TripDetail
│   │   │                        # TripPlan / Profile / Settings
│   │   ├── stores/              # auth / trip
│   │   ├── utils/               # labels / markdown
│   │   ├── router/index.ts  types/index.ts
│   │   └── App.vue  main.ts  style.css
│   ├── package.json  tsconfig.json  vite.config.ts
│   ├── tailwind.config.js  postcss.config.js
│   ├── Dockerfile
│   └── nginx.conf
│
├── .env.example                # 环境变量模板（根目录，后端与 Docker 共用）
├── docker-compose.yml
├── docker-compose.prod.yml
└── README.md
```

## Agent 工作流

采用 **tool-calling（ReAct）循环**：模型自行决定是否调用工具、调用哪些、调用几轮。

```
用户输入旅行需求
      ↓
      ┌──────────────────────────────┐
      ↓                              │
   call_model（已绑定 4 个工具）       │
      │                              │
      ├─ 需要工具 ──> tools 执行 ──────┘
      │                │
      │                ├─ get_weather        高德地图 · 天气预报
      │                ├─ search_attractions 博查 · 联网景点 / 必玩地点
      │                ├─ search_hotels      博查 · 联网酒店住宿
      │                └─ plan_route         高德地图 · 路线规划
      │
      └─ 无需工具 ──> 输出最终回复
```

### 工具说明

| 工具 | 数据来源 | 能力 | 边界 |
| --- | --- | --- | --- |
| `get_weather` | 高德地图天气接口 | 逐日天气、气温、风向风力、出行建议 | 预报能力上限约 4 天 |
| `search_attractions` | 博查 AI 搜索 | 必去/必玩景点、游玩攻略、口碑推荐 | 公开网页内容，无结构化坐标；价格与开放时间需注明参考 |
| `search_hotels` | 博查 AI 搜索 | 酒店/民宿推荐、口碑与参考价格 | **仅能查询，无法在线下单预订** |
| `plan_route` | 高德地图 | 驾车/步行/骑行/公交的真实距离、耗时、分段 | origin/destination 直接传地名，由高德地理编码 |

### 数据可靠性约定

- 所有数据均来自线上 API，**没有任何模拟或占位数据**
- 配置缺失时明确报错，指出缺哪个 Key、去哪里申请，不静默降级
- 工具失败时如实告知原因，并基于其它成功数据继续回答；并行调用时各工具错误互不串扰

### 排查提示

- **博查返回 403**：不一定只是 Key 无效，也可能是账户余额或套餐配额不足。接口会透传上游原始说明，据此到 <https://open.bochaai.com> 控制台确认。该错误本轮不可恢复，Agent 会停止重试该工具而非编造数据。
- **高德 QPS 超限（`10021`）**：Agent 会并行调用多个工具，每个 `plan_route` 内部还要做 2 次地理编码，容易瞬时打满 QPS。`AmapClient` 已对同 Key 请求做**全局串行限速**（`AMAP_MIN_INTERVAL`，默认 0.34s）并对 QPS 错误**指数退避重试**（`AMAP_QPS_RETRY`）。若仍频繁出现，调大 `AMAP_MIN_INTERVAL`。

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境（Python 3.11+）
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（模板在项目根目录）
cp ../.env.example .env
# 填入 DEEPSEEK_API_KEY / OPENAI_API_KEY / QWEN_API_KEY 之一（至少一个）
# 也可启动后在网页「配置」页填写，无需改文件、无需重启，见下文「网页端配置」

# 初始化数据库
python scripts/init_db.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

### 3. 访问

- 前端：<http://localhost:5173>
- 后端 API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

### 4. 必需配置

| 变量 | 用途 | 申请地址 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY`（或 `OPENAI_API_KEY` / `QWEN_API_KEY`） | 大模型对话与工具调用 | 对应厂商开放平台，**任选一个** |
| `AMAP_API_KEY` | 天气查询 / 路线规划 | <https://console.amap.com/dev/key/app>（须选「Web 服务」类型） |
| `BOCHA_API_KEY` | 景点 / 必玩地点 / 酒店检索 | <https://open.bochaai.com> |

后端启动时会自动校验并在日志中打印缺失项；也可随时调 `GET /api/v1/agent/tools/status` 查看当前配置状态。以上三项都可在网页「配置」页填写。

### 5. 运行测试

```bash
cd backend
python -m pytest tests -q          # 单元测试（全离线，不需要 API Key）
```

### 6. 端到端验证（真实调用线上 API）

```bash
cd backend

# 逐个工具打通验证：天气 / 景点 / 酒店 / 路线
python scripts/e2e_check.py

# 全链路验证：HTTP API -> Agent -> LLM -> 多工具编排
#   需先启动服务：uvicorn app.main:app --port 8899
python scripts/e2e_agent.py
```

## 网页端配置

无需编辑 `.env`、无需重启服务：导航栏 **「配置」**（`/settings`）→ 分别填写 **大模型**（供应商 / API Key / 模型名 / Base URL）、**高德地图**（API Key / Base URL）、**博查 AI 搜索**（API Key / Base URL / 检索路径），每区都可单独 **「测试连接」** 与 **「保存」**。

### 配置优先级

```
runtime_config.json  >  .env  >  Settings 字段默认值
```

网页保存的内容写入 `backend/runtime_config.json`（已加入 `.gitignore`，权限 `0600`）。**没有在网页填过的字段继续沿用 `.env`**，两种方式可混用。

### 立即生效机制

`app/llm/client.py`、`app/agent/tools/amap_client.py`、`app/agent/tools/bocha_client.py` 都在**模块导入时**执行了 `settings = get_settings()`，各持有一个固定引用，因此清空 `lru_cache` 无效（新对象生成了，但模块仍指向旧对象）。

由于 `get_settings()` 返回的是**同一个可变对象**，`apply_overrides()` 直接对该单例 `setattr`，所有持有者同步看到新值：LLM 客户端是全局单例，需 `reset_llm_client()` 重建；高德 / 博查客户端在每次工具调用时新建并读取 settings，自动生效。服务重启后由 `app/main.py` 的 lifespan 在配置自检**之前**重新应用，保证重启不丢配置。

### 密钥安全

- **只读不改**：`GET /api/v1/settings/providers` 只返回打码值（如 `sk-1****abcd`），明文永不离开服务端
- **白名单**：只能改 15 个允许字段，`DATABASE_URL`、`SECRET_KEY` 等不在白名单内，直接调接口也会被 422 拒绝
- **输入框留空 = 保持原值**，无需回填已保存的 Key；清空需显式点「清除已保存的 Key」（二次确认，语义是写入 `null` 以覆盖 `.env`）
- **审计日志**：每次变更记录「哪个用户改了哪些字段」，只记字段名，不记值

### ⚠️ 已知限制：任何登录用户都能改

本功能未做角色限制，任何已登录用户都能修改这三组配置。恶意用户可以：

1. 把 LLM 的 Base URL 指向自己的服务器，之后所有用户的对话都会流经它
2. 替换高德 / 博查 Key，观察他人的查询内容
3. 填入无效值，让整个应用对所有人生效地不可用

**本机自用**场景下可接受。对外部署前建议二选一加固：

- 给 `User` 加 `is_admin` 字段，仅管理员可访问（在 `app/api/settings.py` 的依赖里加校验）
- 或在 `app/api/settings.py` 中限制仅 `127.0.0.1` 可调用

## 行程落地：导出 PDF / 保存到「我的行程」

完整行程生成后，AI 回复下方会出现「生成 PDF 行程」与「保存到我的行程」两个按钮，且仅在回复看起来是完整行程时显示（正文 ≥ 400 字符且含「Day / 行程」）。

**导出 PDF**（`POST /api/v1/agent/export/pdf`）

- ReportLab 将 Markdown 忠实排版为 PDF，支持标题、嵌套列表、表格、引用、代码块与行内强调
- 版面极简：顶部只有标题与生成时间，底部只有页码，正文就是模型输出的 Markdown 本身
- 中文字体内置于 `backend/app/assets/fonts/`（Noto Sans SC，SIL OFL 1.1，见同目录 `OFL.txt`），**加粗是真正的 Bold 字重**；字体按需子集化，PDF 体积约 170KB，输出为真实文本，可选中、可搜索
- 内置字体不含 emoji 字形，直接输出会渲染成**空白空洞**。因此 `⚠️ / 💡 / 📌` 会转成 `【注意】/【提示】/【备注】`，其余装饰性 emoji 予以剔除；并会按字体实际覆盖范围逐字符兜底，确保不留空洞

**保存到「我的行程」**

- 两个端点：`POST /api/v1/trips/plan/extract` 只做推断、不落库，返回弹窗预填值；`POST /api/v1/trips/from-plan` 创建行程并把正文写入 `generated_plan`
- 需要确认弹窗：`Trip` 的 `title / destination / start_date / end_date` 均为必填，而出发日期无法从对话可靠得知，因此把推断结果交给用户确认
- 字段推断见 `app/services/plan_extract.py`（纯函数、无 LLM 依赖）：目的地取自天气接口城市或工具调用的 `city`，天数取正文 `Day N` 最大编号或用户原话，人数 / 预算 / 日期取用户原话；推断不出来时留空并提示补填

## 会话管理

「智能规划」页左侧是会话栏，历史咨询按**最近使用**倒序排列，点击即可切回继续追问。

- **落库持久化** — 会话与消息存于 `conversations` / `conversation_messages`，重启后仍在（早期版本把历史放在进程内存里，重启即丢）
- **自动标题** — 取首条提问前 30 字作为会话名，提问里的 Markdown 标记会被清掉
- **会话隔离** — Agent 的上下文只从**当前会话**加载，几次无关的咨询不会互相污染；本轮提问会从历史里排除，避免同一句话被送进模型两次
- **可收缩** — 会话栏可折成窄条（选择记在 `localStorage`）；窄屏（≤860px）下改为抽屉，从聊天区顶部的「会话」按钮唤出

接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/agent/conversations` | 会话列表（含消息数与末条摘要） |
| `GET` | `/api/v1/agent/conversations/{id}` | 会话详情与全部消息 |
| `DELETE` | `/api/v1/agent/conversations/{id}` | 删除会话（连同消息） |

`POST /api/v1/agent/chat` 接受可选的 `conversation_id`：不传则开新会话，响应里回传新会话 ID。该接口不会自动创建空会话——点「新对话」只是清空界面，发出第一条消息后才落库。

## Docker 部署

```bash
cp .env.example .env
# 编辑 .env 填入 API Key

docker-compose up -d        # 启动所有服务
docker-compose logs -f      # 查看日志
docker-compose down         # 停止服务
```

服务端口：前端 `5173`、后端 `8000`、PostgreSQL `5432`。

## API 示例

```bash
# 用户注册
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "email": "test@example.com", "password": "123456"}'

# 登录获取 Token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -F "username=test" \
  -F "password=123456"

# AI 旅行规划
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "我想去日本东京，4月份，5天，2人，预算2万"}'

# 行程导出 PDF（返回二进制流，浏览器会直接下载）
curl -X POST http://localhost:8000/api/v1/agent/export/pdf \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "## Day 1\n\n- 浅草寺", "title": "东京 5 天行程", "destination": "东京"}' \
  -o itinerary.pdf
```

## License

MIT
