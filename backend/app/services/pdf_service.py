"""行程 PDF 导出服务（ReportLab）

把 AI 生成的 Markdown 行程渲染成一份**文字可选中、可搜索**的 PDF。

## 设计取向：忠实呈现 Markdown，不做花哨装饰

早期版本在页首加了品牌色横幅、单独的天气速览表与结尾免责声明，结果是：
横幅配色与正文风格割裂，天气信息与正文里的天气表**重复出现**。
现在改为极简：顶部只有一行标题与生成时间，底部只有页码，正文就是模型输出的
Markdown 本身。

## 字体

内置 `assets/fonts/NotoSansSC-{Regular,Bold}.ttf`（SIL OFL 1.1，见同目录 OFL.txt）：

- **真粗体**：`**重点**` 映射到 Bold 字重，而不再是用颜色冒充加粗
- TrueType(glyf) 轮廓 —— ReportLab **不支持 CFF/PostScript 轮廓**，所以不能直接用
  官方发行的 OTF；这两个 TTF 是由 OTF 转换而来
- 字体已按需**子集化**，并覆盖 Unicode 的货币/箭头/几何/标点等符号区
- 文件缺失时自动回退到 ReportLab 内置 CID 字体 `STSong-Light`，保证服务不会因缺文件而挂掉

## 无法渲染的字符（emoji）

内置字体不含 emoji 字形；若直接输出，emoji 会变成**空洞**（实测每处 emoji 渲染为 0 墨迹，
表现为标题与引用前多出一段空白）。因此这里做两步处理：

1. **有含义的 emoji 转成文字标记**（`⚠️`→`【注意】`、`💡`→`【提示】`、`📌`→`【备注】`）
2. 其余 emoji 与不可渲染字符**按字体实际能力逐字符剔除**

第 2 步是通用的：它逐个字符比对字体的 cmap，而不只是维护一张 emoji 清单，
因此将来出现任何新字符都不会再变成空洞。
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ 常量

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
REGULAR_TTF = FONT_DIR / "NotoSansSC-Regular.ttf"
BOLD_TTF = FONT_DIR / "NotoSansSC-Bold.ttf"

FONT_FAMILY = "NotoSansSC"
FALLBACK_FONT = "STSong-Light"      # ReportLab 内置简体中文 CID 字体（无粗体字形）

PAGE_SIZE = A4
MARGIN_X = 48
MARGIN_TOP = 48
MARGIN_BOTTOM = 52
AVAIL_WIDTH = PAGE_SIZE[0] - MARGIN_X * 2
CELL_FONT_SIZE = 9.5                # 表格字号（列宽计算需与之保持一致）

# 配色沿用前端「墨色 + 品红」的编辑风，而不是通用的商业蓝
INK = colors.HexColor("#0e1b22")
INK_2 = colors.HexColor("#4a5d66")
MUTED = colors.HexColor("#6b7e86")
RULE = colors.HexColor("#b9c6c6")
RULE_LIGHT = colors.HexColor("#d3dcda")
ACCENT = colors.HexColor("#c0266b")
CODE_INK = colors.HexColor("#a21c59")
CODE_BG = colors.HexColor("#eef2f1")


# ------------------------------------------------------------------ 字体加载

class _FontState:
    """字体加载结果（惰性初始化一次）"""

    def __init__(self) -> None:
        self.ready = False
        self.regular = FALLBACK_FONT
        self.bold = FALLBACK_FONT
        # 字体实际支持的码位；None 表示未知（回退字体不做能力过滤）
        self.supported: Optional[Set[int]] = None


_state = _FontState()


def _load_ttf_support(name: str) -> Optional[Set[int]]:
    """取出 TTF 支持的码位集合（用于剔除不可渲染字符）"""
    try:
        face = pdfmetrics.getFont(name).face
        table = getattr(face, "charToGlyph", None)
        if isinstance(table, dict) and table:
            return {int(cp) for cp in table.keys()}
    except Exception as e:  # pragma: no cover - 仅作能力探测，失败不影响出图
        logger.warning("⚠ 无法读取字体覆盖范围（%s）：%s", name, e)
    return None


def _ensure_fonts() -> _FontState:
    """注册字体（只做一次）：优先内置 TTF，缺失则回退 CID"""
    if _state.ready:
        return _state

    try:
        if not (REGULAR_TTF.exists() and BOLD_TTF.exists()):
            raise FileNotFoundError(f"缺少字体文件：{REGULAR_TTF.name} / {BOLD_TTF.name}")

        pdfmetrics.registerFont(TTFont(FONT_FAMILY, str(REGULAR_TTF)))
        pdfmetrics.registerFont(TTFont(f"{FONT_FAMILY}-Bold", str(BOLD_TTF)))
        # 注册字体族，使 <b> 能切到真正的 Bold 字重
        pdfmetrics.registerFontFamily(
            FONT_FAMILY,
            normal=FONT_FAMILY,
            bold=f"{FONT_FAMILY}-Bold",
            italic=FONT_FAMILY,             # 无独立斜体，汉字本身也不宜倾斜
            boldItalic=f"{FONT_FAMILY}-Bold",
        )
        _state.regular = FONT_FAMILY
        _state.bold = f"{FONT_FAMILY}-Bold"
        _state.supported = _load_ttf_support(FONT_FAMILY)
        logger.info(
            "🔤 PDF 字体已加载：%s（覆盖 %s 个码位）",
            REGULAR_TTF.name,
            len(_state.supported) if _state.supported else "未知",
        )
    except Exception as e:
        # 回退到 CID 字体：排版仍可用，只是没有真粗体、且需过滤更多字符
        logger.warning("⚠ 内置 PDF 字体不可用（%s），回退到 %s", e, FALLBACK_FONT)
        pdfmetrics.registerFont(UnicodeCIDFont(FALLBACK_FONT))
        pdfmetrics.registerFontFamily(
            FALLBACK_FONT, normal=FALLBACK_FONT, bold=FALLBACK_FONT,
            italic=FALLBACK_FONT, boldItalic=FALLBACK_FONT,
        )
        _state.regular = FALLBACK_FONT
        _state.bold = FALLBACK_FONT
        _state.supported = None

    _state.ready = True
    return _state


# ------------------------------------------------------------------ 字符处理

# 有含义的 emoji -> 文字标记。这些符号承载语义（警告/提示/备注），
# 直接删掉会丢失信息，因此转成中文标记。
_EMOJI_LABELS: Sequence[Tuple[str, str]] = (
    (r"[⚠❗❕]\uFE0F?", "【注意】"),
    (r"[\U0001F4A1]", "【提示】"),          # 💡
    (r"[\U0001F4CC\U0001F4CD]", "【备注】"),  # 📌 📍
    (r"[\U0001F449\U0001F448]", ""),          # 👉 👈 引导手指，无信息量
)

# 不可渲染字符的范围（emoji 与变体选择符等）。
# 注意：这只覆盖已知的 emoji；真正的兜底是下面按字体 cmap 做的逐字符过滤。
_EMOJI_RE = re.compile(
    "[" 
    "\U0001F000-\U0001FAFF"   # 麻将/扑克/表情/交通/补充符号等主要 emoji 区
    "\U0001F1E6-\U0001F1FF"   # 区域指示符（国旗）
    "\U00002B00-\U00002BFF"   # 杂项符号与箭头
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "\uFE00-\uFE0F"           # 变体选择符
    "\u200D"                  # 零宽连接符
    "\u20E3"                  # 组合包围键帽
    "\u2B50\u2B55"            # 星/圆
    "]"
)


def _replace_meaningful_emoji(text: str) -> str:
    """把有语义的 emoji 换成文字标记"""
    for pattern, label in _EMOJI_LABELS:
        # 连同其后的空白一起替换，避免产生「【注意】 回程」这样的悬空空格
        text = re.sub(f"{pattern}\\s*", label, text)
    return text


def _filter_unsupported(text: str) -> str:
    """剔除字体无法渲染的字符，并清理因此产生的多余空白

    这是**通用兜底**：直接查字体的 cmap，而不是维护 emoji 清单，
    因此任何新增的不可渲染字符都不会再变成空洞。
    """
    if not text:
        return text
    text = _replace_meaningful_emoji(text)
    text = _EMOJI_RE.sub("", text)

    supported = _state.supported
    if supported is not None:
        dropped = {ch for ch in text if ch not in " \t" and ord(ch) not in supported}
        if dropped:
            logger.debug("🔤 已剔除字体不支持的字符：%s", "".join(sorted(dropped)))
            text = "".join(ch for ch in text if ch in " \t" or ord(ch) in supported)

    # 清理：合并重复空格、去掉行首尾空格（emoji 被删后常留下前导空洞）
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ------------------------------------------------------------------ 行内标记

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _escape(text: str) -> str:
    """转义 XML 特殊字符（必须先做，再插入我们自己的标签）"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """行内 Markdown -> ReportLab 标签（含真粗体）"""
    t = _escape(_filter_unsupported(text))
    # 行内代码：浅底 + 强调色（无等宽中文字体，故不走 <font face>）
    t = re.sub(r"`([^`]+)`", rf'<font color="#a21c59">\1</font>', t)
    t = _LINK_RE.sub(r'<link href="\2" color="#4a5d66"><u>\1</u></link>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)          # 真粗体
    t = re.sub(r"(?<![*\w])\*(?!\s)([^*]+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", t)
    return t


# ------------------------------------------------------------------ 样式

def _styles(fonts: _FontState) -> Dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "body", fontName=fonts.regular, fontSize=10.5, leading=17.5,
        textColor=INK, alignment=TA_LEFT, spaceAfter=7, wordWrap="CJK",
    )
    mk = lambda name, **kw: ParagraphStyle(name, parent=base, **kw)  # noqa: E731
    return {
        "body": base,
        # 标题一律用真粗体 + 墨色，靠字号与字重建立层级（不再用大面积彩色）
        "h1": mk("h1", fontSize=19, leading=27, spaceBefore=2, spaceAfter=9,
                 keepWithNext=True),
        "h2": mk("h2", fontSize=14.5, leading=22, spaceBefore=15, spaceAfter=7,
                 keepWithNext=True),
        "h3": mk("h3", fontSize=12, leading=19, textColor=INK_2,
                 spaceBefore=12, spaceAfter=5, keepWithNext=True),
        "h4": mk("h4", fontSize=11, leading=18, textColor=INK_2,
                 spaceBefore=9, spaceAfter=4, keepWithNext=True),
        # bulletFontName 必须显式指定：ReportLab 默认用 Helvetica 画项目符号，
        # 而 Helvetica 是未嵌入的标准字体、没有 ToUnicode 映射，
        # 导致复制/搜索 PDF 时项目符号变成控制字符 U+007F
        "bullet": mk("bullet", leftIndent=16, bulletIndent=4, spaceAfter=3.5,
                     bulletFontName=fonts.regular, bulletFontSize=10.5),
        "quote": mk("quote", leftIndent=12, textColor=INK_2, spaceAfter=0, spaceBefore=0),
        "code": mk("code", fontSize=9.5, leading=15, spaceAfter=0, spaceBefore=0),
        "cell": mk("cell", fontSize=CELL_FONT_SIZE, leading=14.5, spaceAfter=0,
                   spaceBefore=0),
        "cell_head": mk("cell_head", fontSize=CELL_FONT_SIZE, leading=14.5,
                        spaceAfter=0, spaceBefore=0),
        # 极简页首：标题一行 + 生成时间一行
        "title": mk("title", fontSize=20, leading=28, spaceAfter=3, spaceBefore=0),
        "meta": mk("meta", fontSize=9, leading=14, textColor=MUTED,
                   spaceAfter=0, spaceBefore=0),
    }


# ------------------------------------------------------------------ Markdown 解析

_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d{1,3})[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)(.*)$")


def _split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_start(lines: Sequence[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    if "|" not in lines[i]:
        return False
    return bool(_TABLE_SEP_RE.match(lines[i + 1])) and "|" in lines[i + 1]


def _next_content_line(lines: Sequence[str], i: int) -> Optional[str]:
    """取 i 之后第一条非空行（用于判断分隔线是否紧邻标题）"""
    for j in range(i + 1, len(lines)):
        if lines[j].strip():
            return lines[j]
    return None


def _display_width(text: str) -> int:
    """按**显示宽度**计量：中日韩/全角字符算 2，拉丁与数字算 1

    直接用 `len()` 会低估中文占宽（「数据来源」看着 4 字符，实际占 8 个半角位），
    导致「数据来源」被折成「数据来 / 源」。这里先把 Markdown 标记剥掉再计量。
    """
    plain = re.sub(r"[*`~]", "", text)
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in plain
    )


def _column_widths(rows: List[List[str]]) -> List[float]:
    """按各列内容的实际占宽分配列宽

    早期实现对 ≥3 列一律均分，导致「段 / 城市」这类短列被撑开、
    长句列被挤压换行难看。现在：
    - **表头必须单行放得下**，据此计算每列下限
    - 剩余空间按各列最长内容的显示宽度加权分配
    """
    ncol = len(rows[0]) if rows else 1
    if ncol <= 1:
        return [AVAIL_WIDTH]

    # 表头是每列的"必读"内容：宽度下限 = 表头单行所需宽度
    pad = 14.0
    char_w = CELL_FONT_SIZE / 2
    mins = [
        _display_width(rows[0][c] if c < len(rows[0]) else "") * char_w + pad
        for c in range(ncol)
    ]

    weights: List[float] = []
    for c in range(ncol):
        longest = max((_display_width(r[c]) if c < len(r) else 0) for r in rows)
        # 下限避免极短列被压到不可读；上限避免单列吃掉整行
        weights.append(min(max(longest, 6), 140))

    spare = AVAIL_WIDTH - sum(mins)
    if spare <= 0:
        # 表头总宽已超出版心：等比压缩（极端情况仍优于溢出）
        scale = AVAIL_WIDTH / sum(mins)
        return [m * scale for m in mins]

    total = sum(weights)
    return [m + spare * w / total for m, w in zip(mins, weights)]


def _build_table(rows: List[List[str]], styles: Dict[str, ParagraphStyle]) -> LongTable:
    """构造表格（表头加粗、跨页重复表头、无重边框）"""
    widths = _column_widths(rows)
    data: List[List[Any]] = []
    for r, row in enumerate(rows):
        style = styles["cell_head"] if r == 0 else styles["cell"]
        data.append([Paragraph(_inline(c), style) for c in row])

    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        # 只保留横向分隔线，比四边框网格更干净、更易读
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _md_flowables(md: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    """Markdown -> ReportLab flowable 列表"""
    flow: List[Any] = []
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    para_buf: List[str] = []

    def flush_para() -> None:
        if para_buf:
            text = _filter_unsupported(" ".join(para_buf).strip())
            if text:
                flow.append(Paragraph(_inline(text), styles["body"]))
            para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        if _FENCE_RE.match(line):
            flush_para()
            code_lines: List[str] = []
            i += 1
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1
            if code_lines:
                body = "<br/>".join(
                    _escape(_filter_unsupported(cl)).replace(" ", "&nbsp;") or "&nbsp;"
                    for cl in code_lines
                )
                box = Table([[Paragraph(body, styles["code"])]], colWidths=[AVAIL_WIDTH])
                box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                flow.extend([box, Spacer(1, 8)])
            continue

        # 表格
        if _is_table_start(lines, i):
            flush_para()
            header = _split_row(lines[i])
            i += 2
            rows: List[List[str]] = [header]
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            ncol = len(header)
            rows = [(r + [""] * ncol)[:ncol] for r in rows]
            flow.extend([_build_table(rows, styles), Spacer(1, 9)])
            continue

        # 空行
        if not stripped:
            flush_para()
            i += 1
            continue

        # 水平线：模型常在每个大标题前加 `---`，此时紧邻标题，
        # 与标题自身的间距重复，直接略过以免版面被切成碎片
        if _HR_RE.match(line):
            flush_para()
            nxt = _next_content_line(lines, i)
            if not (nxt and _HEADING_RE.match(nxt)):
                flow.extend([Spacer(1, 5),
                             HRFlowable(width="100%", thickness=0.6, color=RULE_LIGHT),
                             Spacer(1, 5)])
            i += 1
            continue

        # 标题
        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            level = len(heading.group(1))
            text = _filter_unsupported(heading.group(2).strip())
            if text:
                key = {1: "h1", 2: "h2", 3: "h3"}.get(level, "h4")
                flow.append(Paragraph(_inline(text), styles[key]))
                if level == 1:
                    flow.extend([Spacer(1, 3),
                                 HRFlowable(width="100%", thickness=0.8, color=RULE),
                                 Spacer(1, 5)])
            i += 1
            continue

        # 无序列表
        ul = _UL_RE.match(line)
        if ul:
            flush_para()
            indent = len(ul.group(1))
            style = ParagraphStyle(
                f"ul{indent}", parent=styles["bullet"],
                leftIndent=16 + indent * 12, bulletIndent=4 + indent * 12,
            )
            text = _filter_unsupported(ul.group(3))
            if text:
                flow.append(Paragraph(_inline(text), style, bulletText="•"))
            i += 1
            continue

        # 有序列表
        ol = _OL_RE.match(line)
        if ol:
            flush_para()
            indent = len(ol.group(1))
            style = ParagraphStyle(
                f"ol{indent}", parent=styles["bullet"],
                leftIndent=16 + indent * 12, bulletIndent=2 + indent * 12,
            )
            text = _filter_unsupported(ol.group(3))
            if text:
                flow.append(Paragraph(_inline(text), style, bulletText=f"{ol.group(2)}."))
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            flush_para()
            quote: List[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(_filter_unsupported(lines[i].strip().lstrip(">").strip()))
                i += 1
            text = " ".join(q for q in quote if q).strip()
            if text:
                bar = Table([[Paragraph(_inline(text), styles["quote"])]],
                            colWidths=[AVAIL_WIDTH])
                bar.setStyle(TableStyle([
                    ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                flow.extend([bar, Spacer(1, 8)])
            continue

        # 普通段落（合并连续行）
        para_buf.append(stripped)
        i += 1

    flush_para()
    return flow


# ------------------------------------------------------------------ 页眉 / 页脚

def _header_block(
    title: str, meta: str, styles: Dict[str, ParagraphStyle]
) -> List[Any]:
    """极简页首：标题一行 + 生成时间一行，无彩色色块"""
    out: List[Any] = []
    clean_title = _filter_unsupported(title) or "旅行行程规划"
    if clean_title:
        out.append(Paragraph(_inline(clean_title), styles["title"]))
    if meta:
        out.append(Paragraph(_escape(_filter_unsupported(meta)), styles["meta"]))
    out.extend([Spacer(1, 7), HRFlowable(width="100%", thickness=1, color=RULE),
                Spacer(1, 10)])
    return out


def _make_footer(fonts: _FontState):
    def on_page(canvas, doc_):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont(fonts.regular, 8.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(PAGE_SIZE[0] - MARGIN_X, 30, f"第 {doc_.page} 页")
        canvas.setStrokeColor(RULE_LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, 42, PAGE_SIZE[0] - MARGIN_X, 42)
        canvas.restoreState()

    return on_page


# ------------------------------------------------------------------ 对外入口

def build_itinerary_pdf(
    *,
    title: str,
    content: str,
    weather_info: Optional[Dict[str, Any]] = None,
    destination: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> bytes:
    """把 Markdown 行程渲染为 PDF，返回文件字节

    Args:
        title: 文档标题（如「北海 3 天行程」）
        content: AI 生成的 Markdown 行程正文
        weather_info: **已不再渲染**。保留参数是为了不改动 API 契约：
            模型通常会在正文里自己输出天气表，再单独插一张会造成重复。
        destination: 目的地（可选，用于副标题）
        subtitle: 自定义副标题（可选，优先级高于 destination）

    Raises:
        ValueError: 正文为空
    """
    if not (content or "").strip():
        raise ValueError("行程内容为空，无法生成 PDF")

    fonts = _ensure_fonts()
    styles = _styles(fonts)

    doc_title = (title or "").strip() or "旅行行程规划"
    bits: List[str] = []
    if subtitle:
        bits.append(subtitle.strip())
    elif destination:
        bits.append(f"目的地：{destination.strip()}")
    bits.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=doc_title,
        author="TravelAI",
        subject="旅行行程规划",
    )

    story: List[Any] = _header_block(doc_title, "　·　".join(bits), styles)
    story.extend(_md_flowables(content, styles))

    footer = _make_footer(fonts)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


__all__ = ["build_itinerary_pdf", "FONT_FAMILY"]
