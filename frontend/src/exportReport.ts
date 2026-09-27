// Exporta o relatório renderizado como um HTML autocontido (CSS do app embutido), legível offline
// e imprimível em PDF pelo navegador. Chips de evidência ficam como texto; as seções dobráveis continuam funcionando.

// Texto original das folhas de estilo (o cssText serializado pelo navegador perde shorthands com var()).
async function appCss(): Promise<string> {
  const out: string[] = []
  for (const sheet of Array.from(document.styleSheets)) {
    const owner = sheet.ownerNode
    if (owner instanceof HTMLStyleElement) {
      out.push(owner.textContent ?? '')
      continue
    }
    if (sheet.href) {
      try {
        const res = await fetch(sheet.href)
        if (res.ok) {
          out.push(await res.text())
          continue
        }
      } catch {
        // segue para o fallback
      }
    }
    try {
      for (const rule of Array.from(sheet.cssRules)) out.push(rule.cssText)
    } catch {
      // folha de outra origem: ignorada
    }
  }
  // fontes/assets do app referenciados por caminho absoluto passam a apontar para o servidor de origem
  return out.join('\n').replace(/url\((['"]?)\/(?!\/)/g, `url($1${location.origin}/`)
}

const EXPORT_CSS = `
html { background: #f4f5f7; }
body { margin: 0; padding: 32px 16px 64px; }
.export-page { max-width: 820px; margin: 0 auto; background: #fff; border: 1px solid #e3e6ea; border-radius: 12px; padding: 32px 36px 44px; font-size: 14px; }
.export-meta { margin-top: 32px; padding-top: 14px; border-top: 1px solid #e3e6ea; font-size: 12px; color: #6b7280; }
button { pointer-events: none; cursor: default; }
@media print {
  html, body { background: #fff; padding: 0; }
  .export-page { border: 0; border-radius: 0; padding: 0; max-width: none; }
}
`

const escape = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export async function buildReportHtml(
  article: HTMLElement,
  meta: { title: string; caseId: string; generatedAt: Date },
): Promise<string> {
  const css = await appCss()
  const doc = article.cloneNode(true) as HTMLElement
  // dobras abertas na impressão e no arquivo: quem baixa quer ver tudo
  doc.querySelectorAll('details').forEach((d) => d.setAttribute('open', ''))
  const when = meta.generatedAt.toLocaleString('pt-BR')
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(meta.title)}</title>
<style>${css}</style>
<style>${EXPORT_CSS}</style>
</head>
<body>
<div class="export-page">
${doc.outerHTML}
<p class="export-meta">Case ${escape(meta.caseId)} · exportado em ${escape(when)} · ambiente de demonstração com dados fictícios. Não representa aprovação de crédito; a decisão é do analista.</p>
</div>
</body>
</html>`
}

export async function downloadReportHtml(article: HTMLElement, meta: { title: string; caseId: string }): Promise<void> {
  const html = await buildReportHtml(article, { ...meta, generatedAt: new Date() })
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${meta.title.replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').toLowerCase() || 'relatorio'}.html`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
