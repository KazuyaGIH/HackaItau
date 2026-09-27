// Transições entre a tela de entrada e a área de trabalho (View Transitions API).
// Sem suporte do navegador, ou com prefers-reduced-motion, a troca acontece direto, sem animação.
import { flushSync } from 'react-dom'

export type Origin = { x: number; y: number }

export function withTransition(kind: 'enter' | 'leave', update: () => void, from?: Origin) {
  const root = document.documentElement
  const apply = () => {
    update()
    window.scrollTo(0, 0)
  }
  if (!document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    apply()
    return
  }
  root.dataset.vt = kind
  // a área de trabalho se abre em círculo a partir deste ponto (o botão Entrar)
  if (from) {
    root.style.setProperty('--vt-x', `${Math.round(from.x)}px`)
    root.style.setProperty('--vt-y', `${Math.round(from.y)}px`)
  }
  const t = document.startViewTransition(() => flushSync(apply))
  void t.finished.finally(() => {
    delete root.dataset.vt
    root.style.removeProperty('--vt-x')
    root.style.removeProperty('--vt-y')
  })
}
