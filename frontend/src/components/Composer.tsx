import { ArrowUp, Check, ChevronDown, LoaderCircle, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ADJUSTABLE, ELIGIBILITY, RISK, STRUCTURING, agentName } from '../squad'

export type ComposerMode = 'new' | 'chat' | 'adjust' | 'working' | 'locked'

interface Props {
  mode: ComposerMode
  placeholder: string
  onSend: (text: string, opts: { adversarial: boolean; target: string }) => void
  autoFocus?: boolean
}

// Sugere o agente a reabrir pelo assunto do ajuste; o analista pode trocar antes de enviar.
function guessTarget(text: string): string {
  if (/produtiv|risco|estresse|cen[aá]rio|pre[cç]o|mitig|alavanc|cobertura/i.test(text)) return RISK
  if (/document|enquadr|elegib|cadastr|certid/i.test(text)) return ELIGIBILITY
  return STRUCTURING
}

export function Composer({ mode, placeholder, onSend, autoFocus }: Props) {
  const [text, setText] = useState('')
  const [adversarial, setAdversarial] = useState(false)
  const [manualTarget, setManualTarget] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const area = useRef<HTMLTextAreaElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const target = manualTarget ?? guessTarget(text)
  const disabled = mode === 'working' || mode === 'locked'

  // altura acompanha o texto (até um limite), como nos chats
  useEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
    el.style.overflowY = el.scrollHeight > 220 ? 'auto' : 'hidden'
  }, [text])

  useEffect(() => {
    if (!menuOpen) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [menuOpen])

  const send = () => {
    const t = text.trim()
    if (!t || disabled) return
    onSend(t, { adversarial, target })
    setText('')
    setManualTarget(null)
  }

  return (
    <form
      className={`composer ${mode}`}
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
    >
      <textarea
        ref={area}
        rows={1}
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Mensagem"
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            send()
          }
        }}
      />
      <div className="composer-bar">
        <div className="composer-tools">
          {mode === 'new' && (
            <button
              type="button"
              className={`pill${adversarial ? ' on' : ''}`}
              aria-pressed={adversarial}
              onClick={() => setAdversarial(!adversarial)}
              title="Inclui um documento com prompt injection pedindo dados de outro cliente"
            >
              <ShieldAlert size={15} />
              Teste de segurança
            </button>
          )}
          {mode === 'adjust' && (
            <div className="target" ref={menuRef}>
              <button
                type="button"
                className="pill"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(!menuOpen)}
              >
                Reabrir {agentName(target)}
                <ChevronDown size={14} />
              </button>
              {menuOpen && (
                <div className="menu" role="menu">
                  <p className="menu-title">Qual agente deve refazer o trabalho?</p>
                  {ADJUSTABLE.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={target === a.id}
                      onClick={() => {
                        setManualTarget(a.id)
                        setMenuOpen(false)
                        area.current?.focus()
                      }}
                    >
                      <span>
                        <strong>{agentName(a.id)}</strong>
                        <span className="muted small">{a.hint}</span>
                      </span>
                      {target === a.id && <Check size={15} />}
                    </button>
                  ))}
                  <p className="menu-foot muted small">Quem depende dele roda de novo, e o Revisor confere no final.</p>
                </div>
              )}
            </div>
          )}
        </div>
        <button type="submit" className="send" disabled={disabled || !text.trim()} aria-label="Enviar">
          {mode === 'working' ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={18} />}
        </button>
      </div>
    </form>
  )
}
