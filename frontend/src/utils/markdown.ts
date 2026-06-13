// Tiny, dependency-free Markdown → HTML for previewing knowledge docs.
// Content is escaped FIRST, then a fixed set of safe tags is re-introduced, so the
// output is safe to bind with v-html (links are restricted to http/https/mailto).

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function inline(s: string): string {
  let t = escapeHtml(s)
  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')
  // bold then italic
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  // links [text](url) — only safe schemes
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, text, url) => {
    const safe = /^(https?:|mailto:)/i.test(url)
    return safe
      ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`
      : text
  })
  return t
}

export function renderMarkdown(src: string): string {
  const lines = (src || '').replace(/\r\n/g, '\n').split('\n')
  const out: string[] = []
  let list: 'ul' | 'ol' | null = null
  let inQuote = false

  const closeList = () => {
    if (list) {
      out.push(`</${list}>`)
      list = null
    }
  }
  const closeQuote = () => {
    if (inQuote) {
      out.push('</blockquote>')
      inQuote = false
    }
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      closeList()
      closeQuote()
      continue
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      closeList()
      closeQuote()
      const n = h[1].length
      out.push(`<h${n}>${inline(h[2])}</h${n}>`)
      continue
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      closeList()
      closeQuote()
      out.push('<hr />')
      continue
    }
    const q = line.match(/^>\s?(.*)$/)
    if (q) {
      closeList()
      if (!inQuote) {
        out.push('<blockquote>')
        inQuote = true
      }
      out.push(`<p>${inline(q[1])}</p>`)
      continue
    }
    const ul = line.match(/^\s*[-*]\s+(.*)$/)
    const ol = line.match(/^\s*\d+\.\s+(.*)$/)
    if (ul || ol) {
      closeQuote()
      const want = ul ? 'ul' : 'ol'
      if (list !== want) {
        closeList()
        out.push(`<${want}>`)
        list = want as 'ul' | 'ol'
      }
      out.push(`<li>${inline((ul ? ul[1] : ol![1]))}</li>`)
      continue
    }
    closeList()
    closeQuote()
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  closeQuote()
  return out.join('\n')
}
