// Login de demonstração: escolher uma das identidades fictícias do backend (governance/identities.json).
// Não há senha nem token — o backend continua autorizando cada acesso pelas permissões do user_id.
import { useCallback, useState } from 'react'
import type { Identity } from './types'

const SESSION_KEY = 'agent-squads.session.v1'

export const ROLE_LABEL: Record<string, string> = {
  credit_analyst: 'Analista de crédito',
  relationship_manager: 'Gerente comercial',
}

export const roleLabel = (role: string) => ROLE_LABEL[role] ?? role.replace(/_/g, ' ')

function load(): Identity | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Identity) : null
  } catch {
    return null
  }
}

export function useSession() {
  const [user, setUser] = useState<Identity | null>(load)

  const signIn = useCallback((u: Identity) => {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(u))
    } catch {
      /* armazenamento indisponível: a sessão só vive nesta aba */
    }
    setUser(u)
  }, [])

  const signOut = useCallback(() => {
    try {
      localStorage.removeItem(SESSION_KEY)
    } catch {
      /* idem */
    }
    setUser(null)
  }, [])

  return { user, signIn, signOut }
}
