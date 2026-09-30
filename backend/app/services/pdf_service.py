"""行程 PDF 导出服务（ReportLab）

把 AI 生成的 Markdown 行程渲染成一份**文字可选中、可搜索**的 PDF。

字体说明（重要）：
- 使用 ReportLab 内置的 Adobe CID 字体 `STSong-Light`（简体中文）。
  **不需要任何字体文件，也不需要系统安装字体**，因此 Docker slim 镜像里同样可用。
- CID 字体不嵌入 PDF（其固有特性），字形由阅读器提供。Chrome、macOS 预览、
  Adobe Reader 均能正常显示，且文字可选中/可搜索。
- 代价：CID 字体只有单一字重，**无法真正加粗**。因此这里把 Markdown 的
  `**重点**` 渲染为主色强调（而非加粗），以保证视觉层级依然清晰。
  这个取舍在 `_inline()` 里有注释说明。

排版支持：标题（# ~ ######）、有序/无序列表（含缩进嵌套）、表格、引用、
水平线、围栏代码块、行内加粗/斜体/代码/链接。
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ------------------------------------------------------------------ 常量

CJK_FONT = "STSong-Light"          # ReportLab 内置简体中文 CID 字体
PAGE_SIZE = A4
MARGIN_X = 46
MARGIN_TOP = 44
MARGIN_BOTTOM = 52
# 可用正文宽度（A4 宽 595.27pt 减去左右边距）
AVAIL_WIDTH = PAGE_SIZE[0] - MARGIN_X * 2

PRIMARY = colors.HexColor("#165DFF")     # 与前端主色一致
INK = colors.HexColor("#1D2129")
MUTED = colors.HexColor("#86909C")
ACCENT = colors.HexColor("#165DFF")
RULE = colors.HexColor("#E5E6EB")
HEADER_BG = colors.HexColor("#F2F3F5")

_font_ready = False


def _ensure_font() -> None:
    """注册中文字体（只做一次）"""
    global _font_ready
    if _font_ready:
        return
    pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))
    # 把 bold/italic 都映射到同一 CID 字体：
    # 让 Markdown 里的 <b>/<i> 标签合法而不抛错（CID 无粗体字形，见模块注释）
    pdfmetrics.registerFontFamily(
        CJK_FONT,
        normal=CJK_FONT,
        bold=CJK_FONT,
        italic=CJK_FONT,
        boldItalic=CJK_FONT,
    )
    _font_ready = True


# ------------------------------------------------------------------ 样式

def _styles() -> Dict[str, ParagraphStyle]:
    _ensure_font()
    base = ParagraphStyle(
        "body",
        fontName=CJK_FONT,
        fontSize=10.5,
        leading=17,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=6,
        wordWrap="CJK",
    )
    return {
        "body": base,
        "h1": ParagraphStyle(
            "h1", parent=base, fontSize=18, leading=26, textColor=PRIMARY,
            spaceBefore=14, spaceAfter=8, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontSize=14.5, leading=22, textColor=INK,
            spaceBefore=12, spaceAfter=6, keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base, fontSize=12.5, leading=19, textColor=colors.HexColor("#4E5969"),
            spaceBefore=10, spaceAfter=5, keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "h4", parent=base, fontSize=11, leading=18, textColor=colors.HexColor("#4E5969"),
            spaceBefore=8, spaceAfter=4, keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base, leftIndent=16, bulletIndent=4, spaceAfter=3,
        ),
        "quote": ParagraphStyle(
            "quote", parent=base, leftIndent=14, textColor=colors.HexColor("#4E5969"),
            borderPadding=(2, 2, 2, 8), spaceBefore=4, spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "code", parent=base, fontSize=9.5, leading=15,
            textColor=colors.HexColor("#1F2937"), spaceAfter=0, spaceBefore=0,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base, fontSize=9.5, leading=15, spaceAfter=0, spaceBefore=0,
        ),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base, fontSize=9.5, leading=15, spaceAfter=0, spaceBefore=0,
            textColor=colors.HexColor("#1D2129"),
        ),
        "title": ParagraphStyle(
            "title", parent=base, fontSize=21, leading=30, textColor=colors.white,
            spaceAfter=0, spaceBefore=0,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base, fontSize=9.5, leading=15,
            textColor=colors.HexColor("#D6E4FF"), spaceAfter=0, spaceBefore=2,
        ),
        "section": ParagraphStyle(
            "section", parent=base, fontSize=12.5, leading=20, textColor=PRIMARY,
            spaceBefore=10, spaceAfter=6, keepWithNext=True,
        ),
    }


# ------------------------------------------------------------------ Markdown 解析

_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d{1,3})[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)(.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _escape(text: str) -> str:
    """转义 XML 特殊字符（必须先做，再插入我们自己的标签）"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """行内 Markdown -> ReportLab 标签

    注意 `**粗体**`：CID 字体无粗体字形，这里用**主色强调**代替加粗，
    这样重点信息在视觉上依然可辨识（见模块注释）。
    """
    t = _escape(text)
    # 行内代码：不能用等宽字体（Courier 无中文字形），改为浅底色 + 深色
    t = re.sub(r"`([^`]+)`", r'<font color="#C7254E">\1</font>', t)
    t = _LINK_RE.sub(r'<link href="\2" color="#165DFF"><u>\1</u></link>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r'<font color="#165DFF">\1</font>', t)
    t = re.sub(r"(?<![*\w])\*(?!\s)([^*]+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", t)
    return t


def _split_row(line: str) -> List[str]:
    """把 `| a | b |` 拆成单元格列表"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_start(lines: Sequence[str], i: int) -> bool:
    """第 i 行是表头且第 i+1 行是分隔行"""
    if i + 1 >= len(lines):
        return False
    if "|" not in lines[i]:
        return False
    return bool(_TABLE_SEP_RE.match(lines[i + 1])) and "|" in lines[i + 1]


def _md_flowables(md: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    """Markdown -> ReportLab flowable 列表"""
    flow: List[Any] = []
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    para_buf: List[str] = []

    def flush_para() -> None:
        if para_buf:
            flow.append(Paragraph(_inline(" ".join(para_buf).strip()), styles["body"]))
            para_buf.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        fence = _FENCE_RE.match(line)
        if fence:
            flush_para()
            code_lines: List[str] = []
            i += 1
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            if code_lines:
                body = "<br/>".join(
                    _escape(cl).replace(" ", "&nbsp;") or "&nbsp;" for cl in code_lines
                )
                box = Table(
                    [[Paragraph(body, styles["code"])]],
                    colWidths=[AVAIL_WIDTH],
                )
                box.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
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
            rows: List[List[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            ncol = len(header)
            data = [[Paragraph(_inline(c), styles["cell_head"]) for c in header]]
            for r in rows:
                r = (r + [""] * ncol)[:ncol]
                data.append([Paragraph(_inline(c), styles["cell"]) for c in r])
            flow.extend([_build_table(data, ncol), Spacer(1, 8)])
            continue

        # 空行
        if not stripped:
            flush_para()
            i += 1
            continue

        # 水平线
        if _HR_RE.match(line):
            flush_para()
            flow.extend([Spacer(1, 4), HRFlowable(width="100%", thickness=0.6, color=RULE),
                         Spacer(1, 8)])
            i += 1
            continue

        # 标题
        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            level = len(heading.group(1))
            key = {1: "h1", 2: "h2", 3: "h3"}.get(level, "h4")
            flow.append(Paragraph(_inline(heading.group(2).strip()), styles[key]))
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
            flow.append(Paragraph(_inline(ul.group(3)), style, bulletText="•"))
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
            flow.append(Paragraph(_inline(ol.group(3)), style, bulletText=f"{ol.group(2)}."))
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            flush_para()
            quote: List[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            bar = Table(
                [[Paragraph(_inline(" ".join(quote)), styles["quote"])]],
                colWidths=[AVAIL_WIDTH],
            )
            bar.setStyle(TableStyle([
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F8FA")),
            ]))
            flow.extend([bar, Spacer(1, 6)])
            continue

        # 普通段落（合并连续行）
        para_buf.append(stripped)
        i += 1

    flush_para()
    return flow


def _build_table(data: List[List[Any]], ncol: int) -> LongTable:
    """构造带表头底色的表格（跨页自动重复表头）"""
    # 列宽：首列略窄，其余均分；按列数简单分配
    if ncol <= 1:
        widths = [AVAIL_WIDTH]
    elif ncol == 2:
        widths = [AVAIL_WIDTH * 0.34, AVAIL_WIDTH * 0.66]
    else:
        widths = [AVAIL_WIDTH / ncol] * ncol
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


# ------------------------------------------------------------------ 页眉 / 页脚

def _header_block(title: str, meta: str, styles: Dict[str, ParagraphStyle]) -> Table:
    """顶部品牌色标题块"""
    head = Table(
        [[Paragraph(_escape(title), styles["title"])],
         [Paragraph(_escape(meta), styles["meta"])]],
        colWidths=[AVAIL_WIDTH],
    )
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (0, 0), 16),
        ("BOTTOMPADDING", (0, -1), (0, -1), 14),
        ("TOPPADDING", (0, 1), (0, 1), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
    ]))
    return head


def _weather_block(weather: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    """天气速览表格"""
    forecasts = weather.get("forecasts") or []
    if not forecasts:
        return []
    header = ["日期", "天气", "气温", "风力"]
    rows: List[List[Any]] = [[Paragraph(_escape(h), styles["cell_head"]) for h in header]]
    for day in forecasts[:7]:
        high, low = day.get("temp_high"), day.get("temp_low")
        temp = "—" if high is None and low is None else f"{'' if low is None else low}~{'' if high is None else high}°C"
        date_text = f"{day.get('date', '')} {day.get('weekday', '')}".strip()
        weather_text = f"{day.get('icon', '')}{day.get('weather', '')}".strip()
        rows.append([
            Paragraph(_escape(date_text), styles["cell"]),
            Paragraph(_escape(weather_text), styles["cell"]),
            Paragraph(_escape(temp), styles["cell"]),
            Paragraph(_escape(day.get("wind") or "—"), styles["cell"]),
        ])
    table = LongTable(rows, colWidths=[AVAIL_WIDTH * 0.30, AVAIL_WIDTH * 0.24,
                                       AVAIL_WIDTH * 0.24, AVAIL_WIDTH * 0.22],
                      repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    out: List[Any] = [Paragraph("🌤 天气速览", styles["section"]), table]
    tips = (weather.get("tips") or "").strip()
    if tips:
        tips_style = ParagraphStyle("tips", parent=styles["body"], fontSize=9.5, leading=15,
                                    textColor=colors.HexColor("#4E5969"), spaceBefore=4)
        out.append(Paragraph(f"💡 {_escape(tips)}", tips_style))
    source = (weather.get("source") or "").strip()
    report_time = (weather.get("report_time") or "").strip()
    if source or report_time:
        note_style = ParagraphStyle("wmeta", parent=styles["body"], fontSize=8.5, leading=13,
                                    textColor=MUTED, spaceBefore=2, spaceAfter=8)
        bits = [b for b in (f"数据来源：{source}" if source else "",
                            f"发布 {report_time}" if report_time else "") if b]
        out.append(Paragraph(_escape(" · ".join(bits)), note_style))
    return out


def _make_footer(doc: SimpleDocTemplate):
    def on_page(canvas, doc_):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont(CJK_FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_X, 30, f"TravelAI 智能行程规划 · 第 {doc_.page} 页")
        canvas.drawRightString(PAGE_SIZE[0] - MARGIN_X, 30, "数据来源：高德地图 / 博查 AI 搜索")
        canvas.setStrokeColor(RULE)
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
        weather_info: 天气卡片数据（可选，来自高德地图）
        destination: 目的地（可选，用于副标题）
        subtitle: 自定义副标题（可选，优先级高于 destination）

    Raises:
        ValueError: 正文为空
    """
    if not (content or "").strip():
        raise ValueError("行程内容为空，无法生成 PDF")

    _ensure_font()
    styles = _styles()

    doc_title = (title or "").strip() or "旅行行程规划"
    bits: List[str] = []
    if subtitle:
        bits.append(subtitle.strip())
    elif destination:
        bits.append(f"目的地：{destination.strip()}")
    bits.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    meta = "　·　".join(bits)

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

    story: List[Any] = [_header_block(doc_title, meta, styles), Spacer(1, 12)]
    if weather_info:
        story.extend(_weather_block(weather_info, styles))
    story.extend(_md_flowables(content, styles))

    # 结尾免责说明
    tail_style = ParagraphStyle("tail", parent=styles["body"], fontSize=8.5, leading=13,
                                textColor=MUTED, spaceBefore=14)
    story.extend([
        HRFlowable(width="100%", thickness=0.6, color=RULE),
        Spacer(1, 4),
        Paragraph(
            "本行程由 TravelAI 依据高德地图（天气 / 路线）与博查 AI 搜索（景点 / 酒店）的实时联网数据自动生成，"
            "景点开放时间、门票与酒店价格可能变动，出行前请以官方信息为准。",
            tail_style,
        ),
    ])

    doc.build(story, onFirstPage=_make_footer(doc), onLaterPages=_make_footer(doc))
    return buffer.getvalue()


__all__ = ["build_itinerary_pdf", "CJK_FONT"]
