# TravelAI（旅行智脑）

> 基于 **LLM 工具调用（Function Calling）· Agent · LangGraph · LangChain** 的智能旅行规划系统

TravelAI 是一款面向旅行者的 AI 驱动旅行规划平台，拥有自主决策能力，能够：

- 🎯 **智能行程规划** — 基于用户偏好和预算自动生成最优路线
- 🤖 **自主工具调用** — 大模型自行决定调用哪些工具、调用几轮（ReAct 循环）
- 🌐 **全线上实时数据** — 天气与路线规划走高德地图，景点 / 必玩地点 / 酒店走博查 AI 搜索（联网检索），无模拟数据
- 💬 **自然语言交互** — 用自然语言描述旅行需求，AI 自动生成完整攻略
- 🔄 **灵活调整** — 支持随时修改行程、添加/删除景点、调整时间
- 📍 **本地化推荐** — 根据目的地推荐美食、住宿、交通

## 技术栈

| 技术 | 用途 | 版本 |
| --- | --- | --- |
| Python | 后端核心语言 | 3.11 / 3.12 |
| FastAPI | 高性能 API 框架 | 0.109+ |
| LangGraph | Agent 工作流编排 | 0.0.40+ |
| LangChain | LLM 链式调用与工具集成 | 0.1.20+ |
| 高德地图 Web 服务 | 天气查询 / 路线规划 | — |
| 博查 AI 搜索 | 景点 / 必玩地点 / 酒店住宿搜索（联网检索） | — |
| SQLAlchemy 2.0 | ORM 数据库访问 | 2.0+ |
| PostgreSQL / SQLite | 主数据库 | PG 15+ / SQLite |
| Vue 3 | 前端渐进式框架 | 3.4+ |
| TypeScript | 前端类型安全 | 5.3+ |
| Pinia | 状态管理 | 2.1+ |
| TailwindCSS | 原子化 CSS | 3.4+ |
| Arco Design Vue | 企业级 UI 组件库 | 2.6+ |
| Vite | 前端构建工具 | 5.0+ |
| ECharts | 地图与数据可视化 | 5.5+ |
| OpenAI / DeepSeek / Qwen | LLM 底座（可切换） | GPT-4 / DeepSeek-V2 / Qwen-Max |

## 项目结构

```
travelai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置文件
│   │   ├── database.py          # 数据库连接
│   │   ├── models/              # SQLAlchemy 模型
│   │   │   ├── user.py  trip.py  booking.py
│   │   ├── schemas/             # Pydantic 模型
│   │   │   ├── user.py  trip.py  agent.py
│   │   ├── api/                 # API 路由
│   │   │   ├── auth.py  trips.py  agent.py
│   │   ├── agent/               # Agent 核心
│   │   │   ├── state.py         # Agent 状态定义
│   │   │   ├── nodes.py         # 节点定义
│   │   │   ├── graph.py         # LangGraph 图构建
│   │   │   ├── memory.py        # 记忆管理
│   │   │   └── tools/           # Agent 工具
│   │   │       ├── spot_tools.py  weather_tools.py
│   │   │       ├── route_tools.py  booking_tools.py
│   │   ├── llm/                 # LLM 客户端
│   │   │   └── client.py
│   │   ├── services/            # 业务逻辑
│   │   │   ├── trip_service.py
│   │   │   ├── plan_extract.py  # 行程字段推断（保存到我的行程）
│   │   │   └── pdf_service.py   # 行程 PDF 导出（Markdown -> PDF）
│   │   └── utils/               # 工具函数
│   │       ├── helpers.py  auth.py
│   ├── tests/                   # 测试
│   │   ├── test_agent.py  test_api.py  test_pdf.py
│   │   ├── test_plan_extract.py  test_trip_from_plan.py
│   ├── scripts/
│   │   ├── init_db.py           # 初始化数据库
│   │   ├── e2e_check.py         # 工具层端到端验证
│   │   └── e2e_agent.py         # 全链路端到端验证
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── api/                 # API 调用
│   │   │   ├── index.ts  auth.ts  trips.ts  agent.ts
│   │   ├── components/          # 组件
│   │   │   ├── common/  trip/  map/
│   │   ├── views/               # 页面
│   │   │   ├── Home.vue  AIChat.vue  TripCreate.vue
│   │   │   ├── TripDetail.vue  TripPlan.vue  Profile.vue
│   │   ├── stores/              # Pinia 状态
│   │   │   ├── auth.ts  trip.ts
│   │   ├── router/index.ts
│   │   ├── types/index.ts
│   │   ├── App.vue
│   │   └── main.ts
│   ├── public/
│   ├── package.json  tsconfig.json  vite.config.ts
│   ├── tailwind.config.js  postcss.config.js
│   ├── Dockerfile
│   └── nginx.conf
│
├── .env.example                # 环境变量模板（根目录，后端与 Docker 共用）
├── .gitignore
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
| `get_weather` | 高德地图天气接口 | 逐日天气、气温、风向风力、出行建议 | 需 `AMAP_API_KEY`；预报能力上限约 4 天 |
| `search_attractions` | 博查 AI 搜索 | 必去/必玩景点、游玩攻略、口碑推荐 | 需 `BOCHA_API_KEY`；为公开网页内容，无结构化坐标，价格与开放时间需注明参考 |
| `search_hotels` | 博查 AI 搜索 | 酒店/民宿推荐、口碑与参考价格 | **仅能查询，无法在线下单预订**；默认限定一年内（`BOCHA_HOTEL_FRESHNESS`） |
| `plan_route` | 高德地图 | 驾车/步行/骑行/公交的真实距离、耗时、分段 | 需 `AMAP_API_KEY`（Web 服务）；origin/destination 直接传地名，由高德地理编码 |

> ⚠️ **博查 403 排查**：若工具报 `HTTP 403`，**不要只怀疑 Key**。博查的 403 有两种原因：
> Key 无效，或**账户余额/套餐配额不足**。接口会透传上游原始说明（例如
> `You do not have enough money or package quota`），据此到
> <https://open.bochaai.com> 控制台确认即可。这类错误属于**本轮请求内不可恢复**，
> Agent 会如实告知用户并停止重试该工具，不会编造景点/酒店数据。

> ⚠️ **高德 QPS 限流**：Agent 会并行调用多个工具，而每个 `plan_route` 内部还要额外做 2 次地理编码，
> 4 条路线瞬间就会打出 12 个请求，很容易触发 `10021 CUQPS_HAS_EXCEEDED_THE_LIMIT`。
> 因此 `AmapClient` 对同 Key 的所有请求做了**全局串行限速**（`AMAP_MIN_INTERVAL`，默认 0.34s/请求）
> 并对 QPS 错误**指数退避重试**（`AMAP_QPS_RETRY`，默认 2 次）。
> 若仍频繁出现，调大 `AMAP_MIN_INTERVAL` 即可。

### 线上模式约定（严格模式）

- **没有任何模拟数据**：所有工具要么返回真实线上数据，要么抛出带明确原因的异常。
- **配置缺失直接报错**：缺 Key 时会明确告知缺哪个、去哪里申请，不会静默降级、不会伪造数据。
- **工具失败不编造**：某个工具失败时，模型只如实说明该工具失败原因，并基于其它成功的数据继续回答。
- **单工具错误隔离**：多个工具并行执行时，各自的错误独立传递，不会相互串扰。

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
# 编辑 .env，填入 DEEPSEEK_API_KEY / OPENAI_API_KEY / QWEN_API_KEY 之一
# （也可以启动后在网页「配置」页里填，无需改文件、无需重启，见下文「网页端配置 API」）

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

> ⚠️ **必须配置 API Key**：本项目为**严格线上模式**，不再提供任何模拟数据兜底。
> 缺少 Key 时相关功能会**直接报错并说明缺哪个 Key**，而不是返回假数据。
>
> 必需配置：
>
> | 变量 | 用途 | 申请地址 | 点击配置按钮进行配置，模型选择一个就可以
> | --- | --- | --- |
> | `DEEPSEEK_API_KEY`（或 `OPENAI_API_KEY` / `QWEN_API_KEY`） | 大模型对话与工具调用 | 对应厂商开放平台 |
> | `AMAP_API_KEY` | 天气查询 / 路线规划 | <https://console.amap.com/dev/key/app>（须选「Web 服务」类型） |
> | `BOCHA_API_KEY` | 景点 / 必玩地点 / 酒店联网检索 | <https://open.bochaai.com> |
>
> 后端启动时会自动校验并打印缺失项；也可随时调 `GET /api/v1/agent/tools/status` 查看当前工具配置状态。

### 4. 运行测试

```bash
cd backend
python -m pytest tests -q          # 单元测试（全离线，不需要 API Key）
```

### 5. 端到端验证（真实调用线上 API）

```bash
cd backend

# 逐个工具打通验证：天气 / 景点 / 酒店 / 路线
python scripts/e2e_check.py

# 全链路验证：HTTP API -> Agent -> LLM -> 多工具编排
#   需先启动服务：uvicorn app.main:app --port 8899
python scripts/e2e_agent.py
```

## Docker 部署

```bash
# 复制环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

服务端口：前端 `5173`、后端 `8000`、PostgreSQL `5432`。

## API 测试

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

## 行程导出 PDF
智能规划产生完整行程后，AI 回复下方会出现 **「生成 PDF 行程」** 按钮（路由 `/api/v1/agent/export/pdf`）。

实现要点：

- **服务端生成**：`app/services/pdf_service.py` 用 ReportLab 把 Markdown 行程排版成 PDF，支持标题、有序/无序列表（含嵌套）、表格、引用、分隔线、代码块、行内强调与链接。
- **中文字体零依赖**：使用 ReportLab 内置的 Adobe CID 字体 `STSong-Light`，**不需要字体文件，也不需要目标机器安装字体**，因此 `python:3.11-slim` 镜像可直接用，无需额外装 `fonts-noto-cjk`。
- **文字是真实文本**：可选中、可搜索、可复制，而不是把页面截图塞进 PDF（代价是文件更小、更高清）。
- **导出入口的触发条件**：仅当回复看起来是完整行程（正文 ≥ 400 字符且含「Day / 行程」）时才追加「导出 PDF 行程」建议操作，避免在「明天天气怎么样」这类短问答下出现无意义的导出按钮。
- **已知取舍**：CID 字体只有一个字重，**无法真正加粗**。因此 Markdown 的 `**重点**` 以主色强调代替加粗（见 `pdf_service._inline()`）。若后续需要真粗体，可改为嵌入系统 TTF/TTC 字体。

## 保存到「我的行程」

智能规划产生完整行程后，AI 回复下方会出现 **「保存到我的行程」** 按钮，点击后弹出确认弹窗，确认即落库到「我的行程」页。

实现要点：

- **两个端点**：
  - `POST /api/v1/trips/plan/extract` —— 只做**推断**，不落库，返回弹窗的预填值；
  - `POST /api/v1/trips/from-plan` —— 真正创建行程，同时把正文写入 `generated_plan`。
- **为什么要确认弹窗**：`Trip` 的 `title / destination / start_date / end_date` 都是必填，而出发日期无法从对话里可靠得知（用户可能只说「4 月份」）。与其静默写入一个猜的日期，不如把推断结果交给用户确认——推断逻辑见 `app/services/plan_extract.py`。
- **字段推断来源**（`app/services/plan_extract.py`，纯函数、无 LLM、无数据库依赖）：
  | 字段 | 推断依据（按优先级） |
  | --- | --- |
  | 目的地 | 天气接口城市 > 工具调用的 `city` 参数 > 「X 天行程」式标题 |
  | 天数 | 正文 `Day N` / `第 N 天` 的最大编号 > 用户原话「N 天」> 天气预报天数 |
  | 人数 | 用户原话「N 人 / N 位」 |
  | 预算 | 用户原话「预算 2 万 / ¥3000 / 3000 元」 |
  | 出发日期 | 用户原话的完整日期 > 正文完整日期 > 「10 月 1 日」> 公历固定假期（国庆/元旦/五一/清明）> 「4 月份」 |
- **宁可留空也不猜错**：目的地推断不出来时返回空串并提示用户补填；正文里「数据发布于 2026-09-30」这类**时间戳不会被当成出发日期**；不存在的日期（如 2 月 30 日）与明显离谱的年份会被丢弃。
- **保存后的落库结构**：`generated_plan = {content, weather_info, source_message, generated_at}`，因此行程详情页能直接展示 AI 规划正文与天气卡片（与「导出 PDF」共用同一份数据）。
- **同时修掉的一个旧问题**：`TripService.save_generated_plan()` 此前从未被任何代码调用，导致「我的行程」页的规划内容一直是空的——现已接入 `/from-plan`。

## 网页端配置 API

无需编辑 `.env`、无需重启服务，直接在网页上配置三组外部依赖：导航栏 **「配置」**（`/settings`）→ 分别填写 **大模型**（供应商 / API Key / 模型名 / Base URL）、**高德地图**（API Key / Base URL）、**博查 AI 搜索**（API Key / Base URL / 检索路径），每区都可单独 **「测试连接」** 与 **「保存」**。

### 配置优先级

```
runtime_config.json  >  .env  >  Settings 字段默认值
```

网页保存的内容写入 `backend/runtime_config.json`（已加入 `.gitignore`，文件权限 `0600`）。**没有在网页填过的字段继续沿用 `.env`**，因此两种方式可以混用；`.env` 依旧是面向部署者的默认值入口。

### 立即生效的实现（这里有个反直觉的点）

`app/llm/client.py`、`app/agent/tools/amap_client.py`、`app/agent/tools/bocha_client.py` 都在**模块导入时**执行了 `settings = get_settings()`，各自固化了一个引用。因此 `get_settings.cache_clear()` **不解决问题**——清缓存只会让下次调用得到一个新的 `Settings` 对象，而那三个模块仍然指向旧对象。

由于 `get_settings()` 返回的是**同一个可变对象**，`app/runtime_config.py` 的 `apply_overrides()` 直接对该单例 `setattr`，所有持有者同步看到新值，无需改动那三个模块。随后：

- **LLM 客户端**是全局单例（`_llm_client`），必须 `reset_llm_client()`；
- **高德 / 博查客户端**在每次工具调用时新建（`AmapClient()` / `BochaClient()`），构造时读取 settings，改完下次调用自动生效，无需重置。

服务重启后由 `app/main.py` 的 lifespan 在**配置自检之前**重新 `apply_overrides()`，保证重启不丢配置。

### 密钥安全

- **只读不改**：`GET /api/v1/settings/providers` 只返回打码值（如 `sk-1****abcd`，保留首尾各 4 位便于辨认），明文永不离开服务端；
- **白名单**：只能改 15 个允许字段。`DATABASE_URL`、`SECRET_KEY` 等**不在白名单内**，即使直接调接口也会被 422 拒绝；
- **输入框留空 = 保持原值**，因此不必回填已保存的 Key；清空需显式点「清除已保存的 Key」（有二次确认，语义是写入 `null` 以覆盖 `.env`）；
- **审计日志**：每次变更记录「哪个用户改了哪些字段」，**只记字段名，不记值**。

### ⚠️ 已知限制：任何登录用户都能改

按当前需求，本功能**未做角色限制**——任何已登录用户都能修改这三组 API 配置。这意味着恶意用户可以：

1. 把 LLM 的 Base URL 指向自己的服务器，之后所有用户的对话都会流经它；
2. 替换高德 / 博查 Key，观察他人的查询内容；
3. 填入无效值，让整个应用对所有人生效地不可用。

这在**本机自用**场景下可接受。若要对外部署，建议二选一加固（改动都很小）：

- 给 `User` 加 `is_admin` 字段，仅管理员可访问本接口（在 `app/api/settings.py` 的依赖里加一道校验）；
- 或在 `app/api/settings.py` 中限制仅 `127.0.0.1` 可调用。

## 与需求文档的差异说明

为让项目可以**实际运行**，对文档中的少量已知问题做了最小必要修正（不改变架构与核心逻辑）：

| 位置 | 原文档写法 | 修正 | 原因 |
| --- | --- | --- | --- |
| `requirements.txt` | `langchain-community==0.0.31` | `0.0.38` | `langchain==0.1.20` 依赖 `langchain-community>=0.0.38`，原组合无法安装 |
| `requirements.txt` | `pytest-asyncio==0.23.4` | `0.23.6` | 原写法要求 `pytest<8`，与 `pytest==8.0.0` 冲突 |
| `models/*.py` | `postgresql.UUID` | `sqlalchemy.Uuid` | 文档默认数据库是 SQLite，PG 专属 UUID 在 SQLite 下无法建表；`Uuid` 在 PostgreSQL 上同样映射为原生 UUID |
| `config.py` | `sqlite:///./travelai.db` | `sqlite+aiosqlite:///./travelai.db` | `create_async_engine` 需要异步驱动；PostgreSQL 生产配置保持不变 |
| `agent/tools/weather_tools.py` | `randint(*temp_range[1:])` | `randint(low, high)` | 原写法会抛 `TypeError`（randint 缺少参数） |
| `views/AIChat.vue` | `<a-spin size="small" />` | `<a-spin :size="16" />` | Arco Spin 的 `size` 为 number 类型 |
| `agent/tools/weather_tools.py` | 墨迹天气 API（`MOJI_API_KEY`） | 高德天气接口（`/v3/weather/weatherInfo`） | 天气与路线统一走高德；高德直接返回结构化预报，无需再让大模型二次规整 |
| `agent/tools/spot_tools.py`、`booking_tools.py` | 高德 POI 搜索 | 博查 AI 搜索（联网检索） | 联网检索能拿到「必玩 / 必去 / 攻略」这类主观推荐信息，POI 列表接口给不了 |
| `agent/tools/tavily_client.py` | Tavily Search API | 由 `bocha_client.py` 取代 | 按需求将联网检索数据源从 Tavily 换成博查 AI 搜索 |
| `app/rag/`、`app/celery_app.py`、`api/spots.py`、`models/spot.py` 等 | 文档中的 RAG 知识库 + Celery 异步队列 + 静态景点库 | 已整体删除 | 项目改为「LLM + 线上工具调用」后，景点/酒店全部走联网检索，RAG 与静态景点库失去消费方；Celery 任务从未被任何代码调用 |
| `docker-compose.yml` | `frontend.volumes:` 为空 | 移除空声明 | YAML 空映射会被解析为 `null` |

此外新增了少量文档未列出但被引用的文件：`app/utils/auth.py`（`api/agent.py` 中 `from app.utils.auth import get_current_user`）、`frontend/src/views/AIChat.vue`（第 7.2 节核心代码对应的页面）。

## License

MIT
