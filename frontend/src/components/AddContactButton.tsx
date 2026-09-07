import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { addConnection } from '../api/social'
import { useAuthStore } from '../stores/auth'

interface Props {
  userId: string
  /** Compact rendering for a row inside a card, where a bordered button would
   *  be louder than the name it sits next to. */
  inline?: boolean
}

/** T3.11.24 — «добавить в контакты», wherever a person is named.
 *
 *  Owner's brief 2026-09-07: the path has to exist «с карточки перевозчика, из
 *  участников сделки, из поиска». Three places, one button — written once
 *  because the three would otherwise disagree about what happens on failure,
 *  and the one that disagrees is always the one nobody opened while testing.
 *
 *  One direction, and nothing is written into the other person's list: adding
 *  somebody says whom *I* keep, and it neither asks them nor tells them.
 *
 *  Never drawn for yourself. An already-added contact is not detected up front
 *  — that would be a request per name on every card — and does not need to be:
 *  the server treats a repeat as the same row and answers with it.
 *
 *  Functions (PROJECT §6.2a):
 *  - `AddContactButton({ userId, inline })` — default export. Called by:
 *    `CarrierPage`, `DealPage`.
 */
export default function AddContactButton({ userId, inline = false }: Props) {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useState(false)
  const [failed, setFailed] = useState(false)

  if (!userId || me?.id === userId) return null

  const add = async () => {
    setBusy(true)
    setFailed(false)
    try {
      await addConnection(userId)
      setAdded(true)
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  if (added) {
    return (
      <span className="text-xs font-body text-navy/40">{t('contacts.contact')}</span>
    )
  }

  return (
    <button
      type="button"
      onClick={add}
      disabled={busy}
      className={
        inline
          ? 'text-xs font-body text-cyan hover:underline disabled:opacity-40'
          : 'text-xs font-display font-medium border border-cyan/40 text-cyan px-3 py-2 min-h-[2.75rem] rounded-field hover:bg-cyan/10 disabled:opacity-40'
      }
    >
      {failed ? t('common.errorGeneric') : t('contacts.add')}
    </button>
  )
}
