/**
 * 行程正文的 Markdown 渲染。
 *
 * AI 写出的行程正文是全站唯一的长文，排版质量直接决定它能不能读。
 * 早期实现把每个换行都变成 <br>，空行因此堆成大片空白；这里改成按块解析：
 * 标题、列表、引用、分隔线各自成块，连续文本行合成一个段落。
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** 行内标记：加粗、斜体、行内代码 */
function inline(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

export function renderMarkdown(content?: string | null): string {
  if (!content) return ''

  const lines = content.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  let listItems: string[] = []
  let paragraph: string[] = []

  const flushList = () => {
    if (listItems.length) {
      out.push(`<ul>${listItems.join('')}</ul>`)
      listItems = []
    }
  }
  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${paragraph.map(inline).join('<br>')}</p>`)
      paragraph = []
    }
  }
  const flush = () => {
    flushList()
    flushParagraph()
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()

    if (!line.trim()) {
      flush()
      continue
    }

    let match: RegExpMatchArray | null

    if ((match = line.match(/^(#{1,6})\s+(.*)$/))) {
      flush()
      const level = Math.min(match[1].length, 3)
      out.push(`<h${level}>${inline(match[2])}</h${level}>`)
      continue
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flush()
      out.push('<hr />')
      continue
    }

    if ((match = line.match(/^\s*[-*+]\s+(.*)$/))) {
      flushParagraph()
      listItems.push(`<li>${inline(match[1])}</li>`)
      continue
    }

    if ((match = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushParagraph()
      listItems.push(`<li>${inline(match[1])}</li>`)
      continue
    }

    if ((match = line.match(/^\s*>\s?(.*)$/))) {
      flush()
      out.push(`<blockquote>${inline(match[1])}</blockquote>`)
      continue
    }

    flushList()
    paragraph.push(line)
  }

  flush()
  return out.join('\n')
}
