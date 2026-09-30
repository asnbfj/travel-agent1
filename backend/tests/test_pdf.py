"""行程 PDF 导出测试

覆盖两层：
1. `app.services.pdf_service.build_itinerary_pdf` —— Markdown 排版与中文字体
2. `POST /api/v1/agent/export/pdf` —— 鉴权、入参校验、下载响应头

关键断言是**从 PDF 里回读文字**：只有文字为真实文本（而非图片）才可能提取出来，
这也正是选择 ReportLab 而非「截图转 PDF」方案的原因。
"""
import io
import re

import pytest
import pypdf
from fastapi.testclient import TestClient

from app.main import app
from app.services.pdf_service import build_itinerary_pdf

SAMPLE_MD = """## 一、天气速览

三天都是晴晒偏热的「多云天」，**适合下海、出海、拍日落**。

## 二、3 天行程

### Day 1｜银滩看海 + 侨港吃海鲜

- **上午**：抵达北海，酒店放行李。
- **傍晚**：侨港风情街，海鲜烧烤与糖水铺。

1. 提前 40 分钟到港
2. 鳄鱼山火山口地貌

| 项目 | 情况 | 参考价 |
|------|------|--------|
| 银滩 | 免费开放 | ¥0 |
| 涠洲岛门票 | 含火山公园 | ¥115 |

> 天气接口最多提供约 4 天预报，请临近再查。

---

`小提示`：上岛船票请提前预订。
"""

WEATHER = {
    "city": "北海",
    "source": "高德地图",
    "report_time": "2026-09-30 09:35:09",
    "tips": "气温较高，注意防暑防晒。",
    "forecasts": [
        {"date": "2026-09-30", "weekday": "周三", "weather": "多云", "icon": "⛅",
         "temp_low": 27, "temp_high": 32, "wind": "南风1-3级"},
        {"date": "2026-10-01", "weekday": "周四", "weather": "多云", "icon": "⛅",
         "temp_low": None, "temp_high": None, "wind": None},
    ],
}


def _extract(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# --------------------------------------------------------------- 服务层测试

def test_pdf_has_valid_header_and_pages():
    pdf = build_itinerary_pdf(title="北海 3 天行程", content=SAMPLE_MD)
    assert pdf.startswith(b"%PDF"), "输出必须是合法的 PDF 文件"
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 1


def test_pdf_text_is_real_and_extractable():
    """文字必须是真实文本（可选中/可搜索），这是选 ReportLab 的核心原因"""
    pdf = build_itinerary_pdf(title="北海 3 天行程", content=SAMPLE_MD)
    text = _extract(pdf)

    for keyword in ["北海 3 天行程", "天气速览", "适合下海、出海、拍日落",
                    "侨港风情街", "鳄鱼山火山口地貌", "涠洲岛门票", "¥115",
                    "请临近再查", "上岛船票请提前预订"]:
        assert keyword in text, f"PDF 中应能提取到「{keyword}」"


def test_pdf_markdown_syntax_does_not_leak():
    """Markdown 标记不应残留在成品里"""
    text = _extract(build_itinerary_pdf(title="T", content=SAMPLE_MD))

    assert "**" not in text, "加粗标记不应出现在成品中"
    assert "##" not in text, "标题标记不应出现在成品中"
    assert "| ---" not in text and "|---" not in text, "表格分隔行不应出现在成品中"
    # 表格单元格内容应保留（且不带竖线）
    assert "免费开放" in text
    assert "含火山公园" in text


def test_pdf_does_not_inject_duplicate_weather_block():
    """天气卡不再单独插入

    模型正文里通常已经自带一张天气表，页首再插一张会让同一份数据出现两次。
    因此 weather_info 只是**保持 API 契约**，不再渲染。
    """
    text = _extract(build_itinerary_pdf(title="北海 3 天行程", content=SAMPLE_MD,
                                        weather_info=WEATHER, destination="北海"))
    # SAMPLE_MD 自带「一、天气速览」标题，因此只应出现 1 次（来自正文）；
    # 若又注入了一张独立天气卡，这里会变成 2 次
    assert text.count("天气速览") == 1, "不应再注入独立的天气速览表"
    assert "防暑防晒" not in text, "天气卡内容不应重复出现在正文之外"
    assert "27~32°C" not in text, "天气卡气温不应出现"
    # 正文自身的天气内容必须保留
    assert "多云天" in text


def test_pdf_accepts_weather_info_without_error():
    """weather_info 参数保留以维持 API 契约，传入也不应报错"""
    pdf = build_itinerary_pdf(title="T", content="正文", weather_info=WEATHER)
    assert pdf.startswith(b"%PDF")


def test_pdf_converts_semantic_emoji_to_text_labels():
    """有语义的 emoji 转成文字标记，而不是丢弃信息"""
    md = "## 行程\n\n> ⚠️ 回程 802km 建议中途休整\n\n- 💡 记得带雨具\n- 📌 涠洲岛先订船票\n"
    text = _extract(build_itinerary_pdf(title="T", content=md))

    assert "【注意】" in text and "回程 802km" in text
    assert "【提示】" in text and "记得带雨具" in text
    assert "【备注】" in text and "先订船票" in text


def test_pdf_drops_decorative_emoji_without_leaving_gaps():
    """装饰性 emoji 被剔除后，不能在行首留下空洞

    内置字体不含 emoji 字形，若原样输出会渲染成**空白**（实测每处 emoji 墨迹为 0），
    表现为标题前凭空多出一段缩进。
    """
    md = "### 🚗 Day 1｜银滩看海\n\n- 🌊 上午：北海银滩\n"
    text = _extract(build_itinerary_pdf(title="T", content=md))

    assert "Day 1｜银滩看海" in text
    assert "上午：北海银滩" in text
    assert not re.search(r"[\U0001F000-\U0001FAFF]", text), "emoji 不应残留"
    assert " Day 1" not in text, "剔除 emoji 后不应留下前导空格"


def test_pdf_no_unrenderable_character_enters_output():
    """按字体实际 cmap 兜底：不支持的字不能进入成品，否则会变成空白"""
    from app.services import pdf_service

    md = "价格 ¥18,600 ｜ ℃ ° → ～ ★ ✓ ① ± ≤ ≈ 「引号」\n"
    text = _extract(build_itinerary_pdf(title="T", content=md))

    fonts = pdf_service._ensure_fonts()
    if fonts.supported is None:
        pytest.skip("未加载内置字体，无法做字符能力校验")
    leftover = [ch for ch in text if ch not in " \n\t" and ord(ch) not in fonts.supported]
    assert not leftover, f"成品中存在字体无法渲染的字符：{leftover}"


def test_pdf_bold_uses_real_bold_weight():
    """加粗必须是真字重，而不是用颜色冒充加粗"""
    from app.services import pdf_service

    fonts = pdf_service._ensure_fonts()
    if fonts.regular == pdf_service.FALLBACK_FONT:
        pytest.skip("未加载内置字体（回退 CID 字体无粗体字形）")
    assert fonts.bold != fonts.regular, "粗体应指向独立的 Bold 字重"


def test_pdf_bullet_markers_survive_text_extraction():
    """项目符号必须能正确复制出来

    ReportLab 默认用 Helvetica 画 bullet，而它是未嵌入的标准字体、没有 ToUnicode
    映射，会让复制/搜索到的项目符号变成控制字符 U+007F。
    """
    text = _extract(build_itinerary_pdf(title="T", content="- 甲\n- 乙\n\n1. 丙\n"))

    assert "\x7f" not in text, "项目符号不应退化成控制字符"
    assert text.count("•") == 2
    assert "1." in text and "丙" in text


def test_pdf_footer_has_page_number():
    text = _extract(build_itinerary_pdf(title="T", content="正文"))
    assert "第 1 页" in text


def test_pdf_table_header_is_not_wrapped():
    """表头必须单行放得下

    曾用 `len()` 估算列宽，低估中文占宽，把「数据来源」折成了「数据来 / 源」。
    """
    md = ("| 段 | 日期 | 距离 | 预计耗时 | 过路费 | 数据来源 |\n"
          "|---|---|---|---|---|---|\n"
          "| 贵阳 → 南宁 | 10/2 08:00 出发 | 600.35 km | 约 7 小时 47 分 | 约 417 元 | 高德地图 |\n")
    text = _extract(build_itinerary_pdf(title="T", content=md))

    assert "数据来源" in text
    assert "数据来\n源" not in text


def test_pdf_without_weather_still_builds():
    pdf = build_itinerary_pdf(title="只有正文", content="## 标题\n\n一段正文。")
    assert pdf.startswith(b"%PDF")
    assert "一段正文" in _extract(pdf)


@pytest.mark.parametrize("content", ["", "   ", "\n\t  \n"])
def test_pdf_rejects_empty_content(content):
    with pytest.raises(ValueError):
        build_itinerary_pdf(title="T", content=content)


def test_pdf_escapes_xml_special_characters():
    """正文含 & < > 时不能破坏排版（ReportLab 用 XML 标记）"""
    pdf = build_itinerary_pdf(title="A & B", content="价格 < 100 且 a & b > c")
    text = _extract(pdf)
    assert "A & B" in text
    assert "< 100" in text and "a & b > c" in text


def test_pdf_handles_h1_through_h6_and_nested_lists():
    md = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6\n\n- 一级\n  - 二级嵌套\n"
    text = _extract(build_itinerary_pdf(title="T", content=md))
    for h in ("H1", "H2", "H3", "H4", "H5", "H6", "一级", "二级嵌套"):
        assert h in text


def test_pdf_table_without_separator_is_treated_as_text():
    """只有表头、没有分隔行的「伪表格」不应被解析成表格而丢内容"""
    text = _extract(build_itinerary_pdf(title="T", content="A | B | C\n这是一行普通文字。"))
    assert "这是一行普通文字。" in text


# --------------------------------------------------------------- 接口层测试

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    import uuid as _uuid
    name = f"pdf_{_uuid.uuid4().hex[:8]}"
    client.post("/api/v1/auth/register",
                json={"username": name, "email": f"{name}@example.com", "password": "123456"})
    resp = client.post("/api/v1/auth/login", data={"username": name, "password": "123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_export_endpoint_returns_pdf(client, auth_headers):
    resp = client.post(
        "/api/v1/agent/export/pdf",
        json={"content": SAMPLE_MD, "title": "北海 3 天行程",
              "destination": "北海", "weather_info": WEATHER},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "银滩看海" in _extract(resp.content)


def test_export_endpoint_sets_utf8_filename(client, auth_headers):
    """中文文件名必须走 RFC 5987 的 filename*，同时提供 ASCII 回退名"""
    resp = client.post(
        "/api/v1/agent/export/pdf",
        json={"content": SAMPLE_MD, "title": "北海 3 天行程"},
        headers=auth_headers,
    )
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert 'filename="travelai-itinerary.pdf"' in disposition
    assert "filename*=UTF-8''" in disposition
    # 中文应以百分号编码出现，而不是直接塞进 header（会导致 latin-1 编码错误）
    assert "%E5%8C%97%E6%B5%B7" in disposition      # 「北海」


def test_export_endpoint_derives_title_from_first_heading(client, auth_headers):
    resp = client.post(
        "/api/v1/agent/export/pdf",
        json={"content": "## 东京 5 天赏樱行程\n\n- 浅草寺"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "东京 5 天赏樱行程" in _extract(resp.content)


def test_export_endpoint_sanitizes_unsafe_filename_chars(client, auth_headers):
    from urllib.parse import unquote

    resp = client.post(
        "/api/v1/agent/export/pdf",
        json={"content": "# 行程", "title": "北海/涠洲岛: 3天*2人?"},
        headers=auth_headers,
    )
    disposition = resp.headers["content-disposition"]
    # 必须解码后再断言：raw header 里的 "filename*=UTF-8''" 本身就含 "*"
    raw = disposition.split("filename*=UTF-8''", 1)[1].strip()
    filename_star = unquote(raw)

    for ch in ["/", ":", "*", "?", "\\"]:
        assert ch not in filename_star, f"解码后的文件名不应包含 {ch}：{filename_star}"
    # 正常内容仍要保留
    assert "北海" in filename_star and "涠洲岛" in filename_star
    assert filename_star.endswith(".pdf")


def test_export_endpoint_ascii_fallback_filename_is_safe(client, auth_headers):
    """ASCII 回退名必须是纯 ASCII，否则会触发 latin-1 编码错误"""
    resp = client.post("/api/v1/agent/export/pdf",
                       json={"content": "# 行程", "title": "北海/涠洲岛: 3天*2人?"},
                       headers=auth_headers)
    fallback = resp.headers["content-disposition"].split('filename="', 1)[1].split('"', 1)[0]
    fallback.encode("ascii")     # 不是纯 ASCII 会抛异常
    assert fallback.endswith(".pdf")


def test_export_endpoint_requires_auth(client):
    resp = client.post("/api/v1/agent/export/pdf", json={"content": "# x"})
    assert resp.status_code == 401


@pytest.mark.parametrize("content", ["", "   "])
def test_export_endpoint_rejects_blank_content(client, auth_headers, content):
    resp = client.post("/api/v1/agent/export/pdf",
                       json={"content": content}, headers=auth_headers)
    assert resp.status_code in (400, 422)
    if resp.status_code == 400:
        assert "为空" in resp.json()["detail"]


def test_export_endpoint_rejects_missing_content(client, auth_headers):
    assert client.post("/api/v1/agent/export/pdf", json={},
                       headers=auth_headers).status_code == 422


# --------------------------------------------------------------- 建议操作

def test_export_action_offered_for_full_itinerary():
    from app.agent.graph import build_suggested_actions, EXPORT_PDF_ACTION
    long_plan = "## Day 1\n" + "行程安排内容。" * 60
    assert EXPORT_PDF_ACTION in build_suggested_actions(long_plan)


@pytest.mark.parametrize("short", [
    "北海明天多云，27~32°C，适合下海。",
    "",
    None,
])
def test_export_action_not_offered_for_short_answers(short):
    """短问答（如只查天气）不该出现导出入口"""
    from app.agent.graph import build_suggested_actions, EXPORT_PDF_ACTION
    assert EXPORT_PDF_ACTION not in build_suggested_actions(short)
