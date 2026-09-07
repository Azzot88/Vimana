import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listConnections,
  lookupUser,
  searchConnections,
  type Connection,
  type FoundUser,
} from '../api/social'
import { inviteRecipient, setRecipient } from '../api/participants'
import MonoText from './MonoText'

interface Props {
  open: boolean
  dealId: string
  onClose: () => void
  onAttached: (displayName: string | null) => void
}

/** T3.11.24 — who is receiving this parcel, chosen rather than typed.
 *
 *  Owner's brief 2026-09-07: «нужно модальное окно чтобы выбрать из списка, с
 *  верхним окном для поиска по разным параметрам» — from contacts, by service
 *  link, or by public key.
 *
 *  **The three ways are not equal, and the form says so.** A contact and a
 *  pasted key both name somebody who already has an account: they are attached
 *  on the spot, and the deal knows who they are. A link is for a person who is
 *  not here yet — nothing is attached, and somebody has to accept it. Merging
 *  the three into one field would have let the sender walk away believing a
 *  recipient is on the deal when nobody has accepted anything, which is the one
 *  misunderstanding this screen exists to prevent.
 *
 *  A key nobody holds is answered by the server with 404, and that is where the
 *  invite path is offered — at the moment it becomes the true answer, not as a
 *  fourth button competing with the others from the start.
 *
 *  Functions (PROJECT §6.2a):
 *  - `RecipientModal({ open, dealId, onClose, onAttached })` — default export.
 *    Called by: `DealVaultPage`.
 */
export default function RecipientModal({
  open,
  dealId,
  onClose,
  onAttached,
}: Props) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [contacts, setContacts] = useState<Connection[]>([])
  /** People found on the platform who are not (yet) my contacts. Kept apart
   *  from the contact list on purpose: «мой контакт» and «нашёлся по почте» are
   *  different degrees of knowing somebody, and merging them would quietly
   *  present a stranger as somebody I keep. */
  const [found, setFound] = useState<FoundUser[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')

  useEffect(() => {
    if (!open) return
    setError('')
    setInviteUrl('')
    setLoading(true)
    listConnections()
      .then(({ data }) => setContacts(data))
      .catch(() => setContacts([]))
      .finally(() => setLoading(false))
  }, [open])

  useEffect(() => {
    if (!open) return
    const needle = query.trim()
    /* Debounced, because the box is typed into letter by letter and every
       letter is a request otherwise. 250 ms is below the pause between words
       and above the gap between keystrokes. */
    const id = window.setTimeout(() => {
      const call = needle ? searchConnections(needle) : listConnections()
      call.then(({ data }) => setContacts(data)).catch(() => setContacts([]))

      /* T3.11.24 — and beyond my own contacts: «поиск сделаем по почте и
         номеру телефона указанному в личном кабинете» plus the handle. The
         server matches those three **whole**, so this fires for anything long
         enough to be one of them and simply finds nobody otherwise. */
      if (needle.length >= 3) {
        lookupUser(needle)
          .then(({ data }) => setFound(data))
          .catch(() => setFound([]))
      } else {
        setFound([])
      }
    }, 250)
    return () => window.clearTimeout(id)
  }, [query, open])

  if (!open) return null

  /** A 64-character hex key, which is what `nostr_pubkey` holds. Checked here
   *  only to decide whether the typed text *can* be a key — the server is the
   *  one that decides whether anybody holds it. */
  const looksLikeKey = /^[0-9a-fA-F]{64}$/.test(query.trim())

  const attach = async (who: { user_id: string } | { npub: string }, name: string | null) => {
    setBusy(true)
    setError('')
    try {
      const { data } = await setRecipient(dealId, who)
      onAttached(data.display_name ?? name)
      onClose()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        // The honest answer, and the moment the invite path becomes the right
        // one: this person is not on the platform.
        setError(t('recipient.notOnPlatform'))
      } else {
        const detail = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : t('recipient.inviteError'))
      }
    } finally {
      setBusy(false)
    }
  }

  const makeLink = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await inviteRecipient(dealId)
      setInviteUrl(data.invite_url)
      try {
        await navigator.clipboard.writeText(data.invite_url)
      } catch {
        /* Clipboard refused (no permission, insecure context) — the link is on
           screen and selectable, which is the part that matters. */
      }
    } catch {
      setError(t('recipient.inviteError'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-modal flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t('recipient.pickerTitle')}
        className="bg-white rounded-card p-6 max-w-md w-full space-y-4 shadow-2xl max-h-[90vh] overflow-y-auto"
      >
        <h3 className="font-display font-semibold text-lg text-navy">
          {t('recipient.pickerTitle')}
        </h3>

        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('recipient.searchPlaceholder') as string}
          aria-label={t('recipient.searchPlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />

        {/* A pasted key is offered as what it is — a person who may or may not
            have an account here — rather than filtered against a list it was
            never going to be in. */}
        {looksLikeKey && (
          <button
            type="button"
            disabled={busy}
            onClick={() => attach({ npub: query.trim() }, null)}
            className="w-full text-left p-3 rounded-field border border-cyan/40 bg-cyan/5 hover:border-cyan disabled:opacity-50"
          >
            <p className="text-sm font-body text-navy">{t('recipient.byKey')}</p>
            <MonoText className="block text-xs text-navy/50 break-all">
              {query.trim()}
            </MonoText>
          </button>
        )}

        {loading ? (
          <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
        ) : contacts.length === 0 ? (
          <p className="text-sm font-body text-navy/50">
            {query.trim() ? t('recipient.noMatches') : t('recipient.noContacts')}
          </p>
        ) : (
          <div className="space-y-2">
            {contacts.map((c) => (
              <button
                key={c.id}
                type="button"
                disabled={busy}
                onClick={() =>
                  attach(
                    { user_id: c.connected_user_id },
                    c.connected_user.display_name,
                  )
                }
                className="w-full flex items-center justify-between gap-3 p-3 rounded-field border border-navy/10 hover:border-cyan text-left disabled:opacity-50"
              >
                <span className="text-sm font-body text-navy truncate">
                  {c.connected_user.display_name}
                </span>
                {c.state === 'close' && (
                  <span className="shrink-0 text-[10px] font-mono uppercase bg-cyan/15 text-cyan px-1.5 py-0.5 rounded">
                    {t('contacts.close')}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Found by email, phone or handle — and shown as a separate group,
            because «мой контакт» and «нашёлся по почте» are different degrees
            of knowing somebody. Anyone already in the list above is dropped
            rather than printed twice. */}
        {found.filter(
          (f) => !contacts.some((c) => c.connected_user_id === f.id),
        ).length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-body font-medium text-navy/40">
              {t('recipient.foundOnPlatform')}
            </p>
            {found
              .filter((f) => !contacts.some((c) => c.connected_user_id === f.id))
              .map((f) => (
                <button
                  key={f.id}
                  type="button"
                  disabled={busy}
                  onClick={() => attach({ user_id: f.id }, f.display_name)}
                  className="w-full flex items-center justify-between gap-3 p-3 rounded-field border border-navy/10 hover:border-cyan text-left disabled:opacity-50"
                >
                  <span className="text-sm font-body text-navy truncate">
                    {f.display_name}
                  </span>
                  {f.handle && (
                    <MonoText className="shrink-0 text-xs text-navy/40">
                      @{f.handle}
                    </MonoText>
                  )}
                </button>
              ))}
          </div>
        )}

        {error && <p className="text-xs font-body text-amber">{error}</p>}

        <div className="border-t border-navy/10 pt-3 space-y-2">
          <p className="text-xs font-body text-navy/50">
            {t('recipient.linkExplainer')}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={makeLink}
            className="text-sm font-body text-cyan hover:underline disabled:opacity-50"
          >
            {t('recipient.makeLink')}
          </button>
          {inviteUrl && (
            <MonoText className="block text-xs text-navy/60 break-all bg-ivory rounded-field p-2">
              {inviteUrl}
            </MonoText>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          className="w-full px-4 py-2 rounded-field border border-navy/15 text-sm font-body text-navy/60 hover:border-navy/40"
        >
          {t('common.close')}
        </button>
      </div>
    </div>
  )
}
