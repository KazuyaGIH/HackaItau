// Fundo em ASCII: curvas de nível de z = sin(x + t)·cos(y − t) + ½ sin(x + y) + ⅓ cos(r − t), desenhadas com caracteres como num mapa topográfico.
// O traço de cada curva segue a direção dela (- / | \); o cursor empurra o relevo. Cor vem do CSS (`color` do canvas;
// `--field-accent` nas curvas-mestras). Pausa fora da tela e com a aba oculta; com prefers-reduced-motion, um quadro só.
import { useEffect, useRef } from 'react'

const FONT_PX = 12
const ROW_PX = 15
const UNIT_PX = 110 // quantos pixels valem 1 em x e y
const LEVELS = 1.6 // curvas por unidade de z
const FPS = 16

function slope(tx: number, ty: number): string {
  let a = (Math.atan2(ty, tx) * 180) / Math.PI
  if (a < 0) a += 180
  if (a < 22.5 || a >= 157.5) return '-'
  if (a < 67.5) return '\\'
  if (a < 112.5) return '|'
  return '/'
}

export function AsciiField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let w = 0
    let h = 0
    let cellW = 7.2
    let raf = 0
    let last = 0
    let onScreen = true
    const start = performance.now()
    const pointer = { x: -1e4, y: -1e4, tx: -1e4, ty: -1e4 }

    const resize = () => {
      const r = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = r.width
      h = r.height
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.font = `${FONT_PX}px 'IBM Plex Mono', ui-monospace, monospace`
      ctx.textBaseline = 'middle'
      ctx.textAlign = 'center'
      cellW = ctx.measureText('M').width
    }

    const draw = (now: number) => {
      const t = still ? 1.3 : (now - start) / 5200
      pointer.x += (pointer.tx - pointer.x) * 0.08
      pointer.y += (pointer.ty - pointer.y) * 0.08
      const cols = Math.ceil(w / cellW)
      const rows = Math.ceil(h / ROW_PX)
      // z no centro de cada célula, com uma borda extra para o gradiente por diferenças centrais
      const W = cols + 2
      const z = new Float32Array(W * (rows + 2))
      for (let j = 0; j < rows + 2; j++) {
        const py = (j - 0.5) * ROW_PX
        const y = py / UNIT_PX
        for (let i = 0; i < W; i++) {
          const px = (i - 0.5) * cellW
          const x = px / UNIT_PX
          const r = Math.hypot(x - w / UNIT_PX / 2, y - h / UNIT_PX / 2)
          const dx = px - pointer.x
          const dy = py - pointer.y
          z[j * W + i] =
            LEVELS *
            (Math.sin(x + t) * Math.cos(y - t) +
              0.5 * Math.sin(x + y) +
              (1 / 3) * Math.cos(r - t) +
              1.1 * Math.exp(-(dx * dx + dy * dy) / (2 * 120 * 120)))
        }
      }
      const cs = getComputedStyle(canvas)
      const ink = cs.color
      const accent = cs.getPropertyValue('--field-accent').trim() || ink
      ctx.clearRect(0, 0, w, h)
      const lines: [number, number, string][] = []
      const major: [number, number, string][] = []
      ctx.fillStyle = ink
      ctx.globalAlpha = 0.45
      for (let j = 0; j < rows; j++) {
        for (let i = 0; i < cols; i++) {
          const k = (j + 1) * W + i + 1
          const v = z[k]
          // gradiente em níveis por pixel
          const gx = (z[k + 1] - z[k - 1]) / (2 * cellW)
          const gy = (z[k + W] - z[k - W]) / (2 * ROW_PX)
          const g = Math.hypot(gx, gy) || 1e-6
          const level = Math.round(v)
          // distância (px) do centro da célula até a curva mais próxima; só desenha se a curva cruza esta célula
          const dist = Math.abs(v - level) / g
          const reach = 0.46 * (Math.abs(gx / g) * cellW + Math.abs(gy / g) * ROW_PX)
          const cx = i * cellW + cellW / 2
          const cy = j * ROW_PX + ROW_PX / 2
          if (dist <= reach) {
            ;(level % 5 === 0 ? major : lines).push([cx, cy, slope(-gy, gx)])
          } else if (i % 6 === 0 && j % 3 === 0) {
            ctx.fillText(i % 12 === 0 && j % 6 === 0 ? '+' : '·', cx, cy)
          }
        }
      }
      ctx.globalAlpha = 1
      for (const [x, y, ch] of lines) ctx.fillText(ch, x, y)
      ctx.fillStyle = accent
      for (const [x, y, ch] of major) ctx.fillText(ch, x, y)
    }

    const loop = (now: number) => {
      raf = requestAnimationFrame(loop)
      if (!onScreen || document.hidden || now - last < 1000 / FPS) return
      last = now
      draw(now)
    }

    const move = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect()
      pointer.tx = e.clientX - r.left
      pointer.ty = e.clientY - r.top
    }

    resize()
    const ro = new ResizeObserver(() => {
      resize()
      draw(performance.now())
    })
    ro.observe(canvas)
    const io = new IntersectionObserver(([e]) => (onScreen = e.isIntersecting))
    io.observe(canvas)
    // a fonte mono pode chegar depois do primeiro quadro
    void document.fonts?.ready.then(() => {
      resize()
      draw(performance.now())
    })
    draw(performance.now())
    if (!still) {
      raf = requestAnimationFrame(loop)
      window.addEventListener('pointermove', move, { passive: true })
    }
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      window.removeEventListener('pointermove', move)
    }
  }, [])

  return <canvas ref={ref} className={className ? `ascii-field ${className}` : 'ascii-field'} aria-hidden="true" />
}
