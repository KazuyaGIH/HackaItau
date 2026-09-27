import { useEffect, useState } from 'react'

// Relógio que só anda enquanto `active` (tempo decorrido da squad, heurística de "analisando").
export function useNow(active: boolean, ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(timer)
  }, [active, ms])
  return now
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 60) return `${s} s`
  return `${Math.floor(s / 60)} min ${s % 60} s`
}

// Anima só o que chegou depois que a conversa foi aberta: o histórico já existente aparece parado.
// As chaves das mensagens carregam o seq do evento (ex.: "e42", "a-e42"); chave sem seq = mensagem local, nova.
export const seqOfKey = (key: string): number | null => {
  const m = /^(?:a-)?e(\d+)/.exec(key)
  return m ? Number(m[1]) : null
}
