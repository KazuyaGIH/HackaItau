// PDF mínimo (uma página, Helvetica) gerado no navegador — usado pelo caso de demonstração de segurança, que anexa
// um laudo de verdade à conversa. Só ASCII: a fonte padrão não precisa de tabela de encoding.
const escape = (s: string) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')

export function makePdf(lines: string[]): Blob {
  const text = lines.map((l) => `(${escape(l)}) Tj T*`).join('\n')
  const stream = `BT\n/F1 11 Tf\n16 TL\n60 760 Td\n${text}\nET`
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  let out = '%PDF-1.4\n'
  const offsets: number[] = []
  objects.forEach((body, i) => {
    offsets.push(out.length)
    out += `${i + 1} 0 obj\n${body}\nendobj\n`
  })
  const xref = out.length
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  out += offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return new Blob([out], { type: 'application/pdf' })
}

export const pdfFile = (name: string, lines: string[]) => new File([makePdf(lines)], name, { type: 'application/pdf' })
