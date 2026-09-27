import { ArrowUp, Check, ChevronDown, FileText, LoaderCircle, Paperclip, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { ADJUSTABLE, ELIGIBILITY, RISK, STRUCTURING, agentName } from '../squad'
import { ACCEPTED_FILES, MAX_FILE_BYTES, type SendOptions } from '../workspace'

// new: primeira mensagem; chat: pergunta livre; reply: resposta ou contexto para o case; adjust: ajuste à squad
export type ComposerMode = 'new' | 'chat' | 'reply' | 'adjust' | 'working' | 'locked'

interface Props {
  mode: ComposerMode
  placeholder: string
  onSend: (text: string, opts: SendOptions) => void
  autoFocus?: boolean
  canAttach?: boolean
}

// Sugere o agente a reabrir pelo assunto do ajuste; o analista pode trocar antes de enviar.
function guessTarget(text: string, hasFiles: boolean): string {
  if (hasFiles || /document|enquadr|elegib|cadastr|certid|matr[ií]cula|arrendamento/i.test(text)) return ELIGIBILITY
  if (/produtiv|risco|estresse|cen[aá]rio|pre[cç]o|mitig|alavanc|cobertura/i.test(text)) return RISK
  return STRUCTURING
}

const size = (bytes: number) =>
  bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`

export function Composer({ mode, placeholder, onSend, autoFocus, canAttach = true }: Props) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [manualTarget, setManualTarget] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const area = useRef<HTMLTextAreaElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const target = manualTarget ?? guessTarget(text, files.length > 0)
  const disabled = mode === 'working' || mode === 'locked'
  const attachable = canAttach && !disabled
  // sem case aberto, anexo sozinho não basta: é preciso descrever a operação
  const canSend = !disabled && (text.trim().length > 0 || (files.length > 0 && mode !== 'new'))

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

  const addFiles = (list: FileList | null) => {
    if (!list) return
    const accepted: File[] = []
    const problems: string[] = []
    for (const f of Array.from(list)) {
      const ok = ACCEPTED_FILES.split(',').some((ext) => f.name.toLowerCase().endsWith(ext))
      if (!ok) problems.push(`${f.name}: use PDF, TXT, MD, CSV ou JSON`)
      else if (f.size > MAX_FILE_BYTES) problems.push(`${f.name}: maior que 2 MB`)
      else accepted.push(f)
    }
    setFileError(problems.length ? problems.join('; ') : null)
    setFiles((prev) => [...prev, ...accepted].slice(0, 5))
  }

  const send = () => {
    if (!canSend) return
    onSend(text.trim(), { target, files })
    setText('')
    setFiles([])
    setFileError(null)
    setManualTarget(null)
  }

  return (
    <form
      className={`composer ${mode}`}
      onSubmit={(e) => {
        e.preventDefault()
        send()
      }}
      onDragOver={(e) => attachable && e.preventDefault()}
      onDrop={(e) => {
        if (!attachable) return
        e.preventDefault()
        addFiles(e.dataTransfer.files)
      }}
    >
      {files.length > 0 && (
        <div className="composer-files">
          {files.map((f, i) => (
            <span key={`${f.name}-${i}`} className="file-chip">
              <FileText size={14} />
              <span className="file-chip-name">{f.name}</span>
              <span className="muted">{size(f.size)}</span>
              <button
                type="button"
                aria-label={`Remover ${f.name}`}
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      )}
      {fileError && <p className="composer-error">{fileError}</p>}
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
          {canAttach && (
            <>
              <button
                type="button"
                className="icon-btn"
                aria-label="Anexar documento"
                title="Anexar documento (PDF, TXT, MD, CSV ou JSON, até 2 MB)"
                disabled={!attachable}
                onClick={() => picker.current?.click()}
              >
                <Paperclip size={17} />
              </button>
              <input
                ref={picker}
                type="file"
                accept={ACCEPTED_FILES}
                multiple
                hidden
                onChange={(e) => {
                  addFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </>
          )}
          {mode === 'adjust' && (
            <div className="target" ref={menuRef}>
              <button
                type="button"
                className="pill"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen(!menuOpen)}
                title="Se a mensagem for um ajuste, este agente refaz o trabalho"
              >
                Ajuste vai para {agentName(target)}
                <ChevronDown size={14} />
              </button>
              {menuOpen && (
                <div className="menu" role="menu">
                  <p className="menu-title">Se for um ajuste, qual agente deve refazer o trabalho?</p>
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
                  <p className="menu-foot muted small">
                    Quem depende dele roda de novo, e o Revisor confere no final. Perguntas são respondidas sem rodar a
                    squad.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
        <button type="submit" className="send" disabled={!canSend} aria-label="Enviar">
          {mode === 'working' ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={18} />}
        </button>
      </div>
    </form>
  )
}
