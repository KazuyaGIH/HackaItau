import { Network } from 'lucide-react'
import type { ReactNode } from 'react'

// Marca do Orquestrador. Pulsa enquanto ele está pensando.
export function OrchestratorMark({ live = false, size = 28 }: { live?: boolean; size?: number }) {
  return (
    <span className={`orch-mark${live ? ' live' : ''}`} style={{ width: size, height: size }} aria-hidden="true">
      <Network size={Math.round(size * 0.54)} strokeWidth={2} />
    </span>
  )
}

interface IconButtonProps {
  label: string
  onClick?: () => void
  disabled?: boolean
  children: ReactNode
  showLabel?: boolean
  pressed?: boolean
}

export function IconButton({ label, onClick, disabled, children, showLabel, pressed }: IconButtonProps) {
  return (
    <button
      type="button"
      className={`icon-btn${showLabel ? ' with-label' : ''}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
    >
      {children}
      {showLabel && <span>{label}</span>}
    </button>
  )
}
