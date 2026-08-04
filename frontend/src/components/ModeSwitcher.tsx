import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'

/**
 * T1.24 — explicit dual role switcher.
 * The button text always names the OPPOSITE mode (never the current one) —
 * current mode is derived from the surrounding UI (dashboard colors, CTAs).
 */
export default function ModeSwitcher() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const switchMode = useAuthStore((s) => s.switchMode)
  const [busy, setBusy] = useState(false)

  if (!user) return null
  // Hide if user can't be in the other mode (e.g. can_carry=false blocks carrier)
  const canBeCarrier = user.can_carry
  const canBeSender = user.can_send
  const isCarrier = user.active_mode === 'carrier'
  const hidden = (isCarrier && !canBeSender) || (!isCarrier && !canBeCarrier)
  if (hidden) return null

  const handleClick = async () => {
    if (busy) return
    setBusy(true)
    try {
      await switchMode()
    } finally {
      setBusy(false)
    }
  }

  // Show opposite mode label; icon hints at the destination role.
  const label = isCarrier ? t('mode.switchToSend') : t('mode.switchToDeliver')
  const icon = isCarrier ? '📤' : '✈️'
  const tint = isCarrier
    ? 'border-amber/40 text-amber hover:bg-amber/10'
    : 'border-cyan/50 text-link hover:bg-cyan/10'

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      title={label as string}
      className={`hidden md:inline-flex items-center gap-1.5 text-xs font-display font-medium border px-3 py-1.5 rounded-field transition-colors disabled:opacity-50 ${tint}`}
    >
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </button>
  )
}
