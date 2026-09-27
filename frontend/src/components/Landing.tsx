// Tela de entrada da demo: login (ID + senha fictícios) e, rolando, um diagrama de como a squad trabalha
// e o comparativo com um agente generalista.
// A senha nunca sai deste componente: o ID é conferido contra as identidades fictícias do backend (GET, sem credenciais).
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api'
import { ART, ART_CREDIT, PRODUCT } from '../brand'
import '../landing.css'
import type { Identity } from '../types'
import { AsciiField } from './AsciiField'
import { Comparison } from './Comparison'
import { HowItWorks } from './HowItWorks'

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
// intervalo entre teclas: base + um pouco de acaso, como uma pessoa digitando
const keystroke = (base: number, spread: number) => wait(base + Math.random() * spread)
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// senha de mentira para o preenchimento da demo: só enfeita o campo, nunca é conferida nem enviada
function fakePassword(): string {
  const abc = 'abcdefghjkmnpqrstuvwxyz23456789'
  const n = crypto.getRandomValues(new Uint8Array(8))
  return Array.from(n, (v) => abc[v % abc.length]).join('')
}

// `from`: centro do botão Entrar, de onde a área de trabalho se abre na animação de entrada
export type SignIn = (u: Identity, from?: { x: number; y: number }) => void

export function Landing({ onSignIn }: { onSignIn: SignIn }) {
  const enterBtn = useRef<HTMLButtonElement>(null)
  const idInput = useRef<HTMLInputElement>(null)
  const pwInput = useRef<HTMLInputElement>(null)
  // cada preenchimento da demo ganha um número; digitar, enviar ou sair da tela invalida o que estiver em curso
  const typing = useRef(0)
  const [ready, setReady] = useState(false)
  // a pintura só "assenta" na primeira abertura; voltando da área de trabalho, ela chega pela view transition
  const [intro] = useState(() => !document.documentElement.dataset.vt)
  const [users, setUsers] = useState<Identity[] | null>(null)
  const [userId, setUserId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.identities().then(setUsers, () => setUsers(null))
    const runs = typing
    return () => {
      runs.current++
    }
  }, [])

  // escolher um ID da demo digita o ID e uma senha qualquer, tecla a tecla, como alguém entrando
  const fillDemo = async (id: string) => {
    const run = ++typing.current
    const live = () => run === typing.current
    const pw = fakePassword()
    setError(null)
    setReady(false)
    if (reducedMotion()) {
      setUserId(id)
      setPassword(pw)
      setReady(true)
      return
    }
    setUserId('')
    setPassword('')
    idInput.current?.focus()
    await wait(80)
    for (let i = 1; i <= id.length && live(); i++) {
      setUserId(id.slice(0, i))
      await keystroke(id[i - 1] === '-' ? 90 : 28, 32)
    }
    if (!live()) return
    await wait(140)
    if (!live()) return
    pwInput.current?.focus()
    for (let i = 1; i <= pw.length && live(); i++) {
      setPassword(pw.slice(0, i))
      await keystroke(30, 30)
    }
    if (!live()) return
    await wait(90)
    if (!live()) return
    enterBtn.current?.focus({ preventScroll: true })
    setReady(true)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    typing.current++
    if (!userId.trim()) {
      setError('Informe o ID de usuário.')
      return
    }
    setError(null)
    setBusy(true)
    try {
      const list = users ?? (await api.identities())
      setUsers(list)
      const found = list.find((u) => u.user_id === userId.trim().toLowerCase())
      if (found) {
        setPassword('')
        const r = enterBtn.current?.getBoundingClientRect()
        onSignIn(found, r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : undefined)
      } else {
        setError(`ID não encontrado. Na demo, use ${list.map((u) => u.user_id).join(' ou ')}.`)
      }
    } catch {
      setError('Não foi possível falar com o servidor. Ele está rodando?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={intro ? 'landing intro' : 'landing'}>
      {/* um fundo só para a página inteira: as seções rolam por cima dele, sem emenda entre elas */}
      <AsciiField className="l-field-bg" />
      <section className="l-hero" aria-labelledby="l-name">
        <div className="l-hero-main">
          <header className="l-id">
            <h1 id="l-name">{PRODUCT}</h1>
            <p className="l-context">orquestração de agentes especialistas</p>
            <p className="l-desc">
              Squads de agentes para análise de crédito, com acesso mínimo aos dados e decisão final humana.
            </p>
          </header>

          <form className="l-form" onSubmit={submit} autoComplete="off" noValidate>
            <label className="l-field">
              <span>ID de usuário</span>
              <input
                ref={idInput}
                className="mono"
                value={userId}
                onChange={(e) => {
                  typing.current++
                  setReady(false)
                  setUserId(e.target.value)
                }}
                placeholder="analyst-001"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                aria-describedby="l-ids"
                required
              />
            </label>
            {users && users.length > 0 && (
              <p id="l-ids" className="l-ids">
                demo:{' '}
                {users.map((u, i) => (
                  <span key={u.user_id}>
                    {i > 0 && ' · '}
                    <button type="button" onClick={() => void fillDemo(u.user_id)}>
                      {u.user_id}
                    </button>
                  </span>
                ))}
              </p>
            )}
            <label className="l-field">
              <span>Senha</span>
              <input
                ref={pwInput}
                type="password"
                value={password}
                onChange={(e) => {
                  typing.current++
                  setPassword(e.target.value)
                }}
                autoComplete="off"
              />
            </label>
            {error && (
              <p className="l-error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className={ready ? 'l-enter ready' : 'l-enter'} disabled={busy} ref={enterBtn}>
              Entrar
            </button>
            <p className="l-note">Ambiente de demonstração · dados fictícios</p>
          </form>
        </div>

        <figure className="l-art">
          <img
            className="l-art-img"
            src={ART}
            alt="Pintura de Leo von Klenze: a Acrópole de Atenas idealizada, com o Partenon e uma multidão na praça em primeiro plano."
          />
          <figcaption className="l-credit">{ART_CREDIT}</figcaption>
        </figure>

        <a className="l-scroll" href="#como-funciona">
          <span>role para ver como funciona</span>
          <span className="l-scroll-arrow" aria-hidden="true">
            ↓
          </span>
        </a>
      </section>

      <HowItWorks />

      <Comparison />

      <footer className="l-foot">
        <pre aria-hidden="true">{'demanda ──▶ orquestrador ──▶ squad ──▶ revisor ──▶ humano'}</pre>
        <p>
          {PRODUCT} · ambiente de demonstração · dados fictícios · nenhuma credencial é enviada ou guardada · pintura em domínio
          público
        </p>
      </footer>
    </div>
  )
}
