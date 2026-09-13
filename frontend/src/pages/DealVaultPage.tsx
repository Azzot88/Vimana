import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, Link } from 'react-router-dom'
import {
  attachExistingFile,
  createMessage,
  listMessages,
  messagesSignature,
  shareAddressInVault,
  type AttachmentKind,
  type E2EParties,
  type VaultMessage,
} from '../api/dealvault'
import api from '../api/client'
import { getDeal, type DealDetail, type DealStatus } from '../api/deals'
import { getTerms, type Terms } from '../api/terms'
import RecipientModal from '../components/RecipientModal'
import SafeFilePicker from '../components/SafeFilePicker'
import { decryptE2E, envelopeParts } from '../lib/threshold'
import { useAuthStore } from '../stores/auth'
import AddressCard, { isAddressCard } from '../components/AddressCard'
import TermsCard from '../components/TermsCard'
import DealAgreementCard from '../components/DealAgreementCard'
import DealStages from '../components/DealStages'
import DealCard from '../components/DealCard'
import DealPage from './DealPage'
import ImageLightbox from '../components/ImageLightbox'
import MonoText from '../components/MonoText'
import ShareAddressModal from '../components/ShareAddressModal'
import { usePrefs } from '../hooks/usePrefs'
import { useLiveBeat } from '../hooks/useLiveBeat'

/** T_UX.7 pt.3 — keys, not labels. The labels themselves were Russian literals
 *  and doubled as the `alt` text on every attachment, so five locales got a
 *  Russian image description read aloud by their screen reader. */
const KIND_KEY: Record<AttachmentKind, string> = {
  handoff_photo: 'chat.kind.handoff_photo',
  receipt_photo: 'chat.kind.receipt_photo',
  doc: 'chat.kind.doc',
  payment_receipt: 'chat.kind.payment_receipt',
  identity_doc: 'chat.kind.identity_doc',
  pre_seal_photo: 'chat.kind.pre_seal_photo',
  cargo_photo: 'chat.kind.cargo_photo',
}

export default function DealVaultPage() {
  const prefs = usePrefs()
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const { dealId } = useParams<{ dealId: string }>()
  const [messages, setMessages] = useState<VaultMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string>('')
  /* T3.11.24 — the recipient picker. Sender-only, like the button that opens
     it: the server refuses anybody else, and a control drawn in order to be
     refused is worse than one that is not drawn. */
  const [recipientOpen, setRecipientOpen] = useState(false)
  /* Not `error`: «получатель добавлен» is good news, and the error strip is
     amber. One state for both would have made every success look like a
     warning. */
  const [notice, setNotice] = useState('')
  const [safeOpen, setSafeOpen] = useState(false)
  /* T3.11.17 — where the deal stands. The stage ladder is drawn from it, and
     it is refetched with the messages so an accepted card moves the stage
     without a reload. */
  const [dealStatus, setDealStatus] = useState<DealStatus>('matched')
  /* T3.11.27 — the deal card replaced the boarding pass, so the screen needs
     the deal and the agreement rather than the status alone. */
  const [deal, setDeal] = useState<DealDetail | null>(null)
  const [terms, setTerms] = useState<Terms | null>(null)
  const [cardOpen, setCardOpen] = useState(true)
  const [preview, setPreview] = useState<{ url: string; alt: string } | null>(null)
  const [shareOpen, setShareOpen] = useState(false)
  const [parties, setParties] = useState<{
    e2e: E2EParties | null
    senderId: string | null
    carrierId: string | null
  }>({ e2e: null, senderId: null, carrierId: null })
  const [decrypted, setDecrypted] = useState<Record<string, string>>({})
  const bottomRef = useRef<HTMLDivElement>(null)
  /* Bumped by the poll. The status and the agreement hang off it as well as off
     `messages.length`, because acknowledging a card changes its state **in
     place**: the list is the same length and the deal has still moved. */
  const [tick, setTick] = useState(0)

  // T3.35 — a card that awaits the other side must not offer this user a
  // button the server will refuse anyway.
  const dealRole: 'sender' | 'carrier' | null =
    user?.id && parties.senderId === user.id
      ? 'sender'
      : user?.id && parties.carrierId === user.id
        ? 'carrier'
        : null

  const load = async () => {
    if (!dealId) return
    try {
      const { data } = await listMessages(dealId, { limit: 100 })
      setMessages((prev) =>
        messagesSignature(prev) === messagesSignature(data.items) ? prev : data.items,
      )
      setError('')
    } catch (err: unknown) {
      /* The server's own words when it has any. «Не удалось загрузить
         сообщения» was every cause collapsed into one sentence — a network
         blip, a sealed vault and «вы не участник этой сделки» read identically,
         and the last of those is the one somebody can actually act on. A
         recipient seeing this had no way to learn which it was, and neither did
         we (owner, 2026-09-12). */
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('chat.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [dealId])

  /* T3.11.27 — the other side moves too (owner's request 2026-09-12). The beat
     itself, and the reasoning behind it, live in `useLiveBeat`; what belongs
     here is only what this screen refetches on it. `tick` is bumped alongside
     the messages because acknowledging a card changes its state **in place** —
     the list is the same length and the deal has still moved. */
  useLiveBeat(() => {
    load()
    setTick((n) => n + 1)
  }, Boolean(dealId))

  /* T3.11.17 — refetched with the messages, not once on mount: accepting a card
     moves the deal to the next stage, and a ladder that only updated on reload
     would leave the person looking at the step they have just finished. */
  useEffect(() => {
    if (!dealId) return
    api
      .get<{
        sender_id: string
        carrier_id: string
        status: DealStatus
        sender_npub: string | null
        carrier_npub: string | null
      }>(`/api/deals/${dealId}`)
      .then(({ data }) => {
        /* T3.11.17 — the stage is read off the status the server keeps, never
           worked out here: a screen with its own opinion about where a deal
           stands is a second answer to a question that must have one. */
        setDealStatus(data.status)
        /* Replaced only when it actually differs. The poll runs this every ten
           seconds, and a fresh object each time changes `parties` by identity —
           which re-runs the decryption effect that depends on it, on every
           message, forever. The parties of a deal do not change; the object
           holding them should not either. */
        setParties((prev) =>
          prev.senderId === data.sender_id &&
          prev.carrierId === data.carrier_id &&
          prev.e2e?.senderNpub === (data.sender_npub ?? undefined) &&
          prev.e2e?.carrierNpub === (data.carrier_npub ?? undefined)
            ? prev
            : {
                e2e:
                  data.sender_npub && data.carrier_npub
                    ? {
                        senderNpub: data.sender_npub,
                        carrierNpub: data.carrier_npub,
                      }
                    : null,
                senderId: data.sender_id,
                carrierId: data.carrier_id,
              },
        )
      })
      .catch(() => {
        // deal-detail fetch is best-effort — plaintext send path still works.
      })
  }, [dealId, messages.length, tick])

  /* T3.11.27 — the agreement, alongside the deal. Refetched with the messages
     for the same reason the status is: confirming the card is a message, and a
     card that only refreshed on reload would keep showing «ждём подтверждения»
     to the person who has just given it. */
  useEffect(() => {
    if (!dealId) return
    getDeal(dealId)
      .then(({ data }) => setDeal(data))
      .catch(() => setDeal(null))
    getTerms(dealId)
      .then((data) => {
        setTerms(data)
        /* Open while it is not agreed by both — that is the first stage. Once
           agreed it folds itself away: the screen is about the parcel from
           then on. A person who opened it by hand is not overruled, because
           this only runs when the answer changes. */
        setCardOpen(data?.card_kind !== 'terms.agreed')
      })
      .catch(() => setTerms(null))
  }, [dealId, messages.length, tick])

  // Try to decrypt e2e messages using own read_package + author's npub.
  // Failures (custodial user, missing extension, corrupt blob) leave the
  // message showing a "🔒 encrypted" placeholder.
  useEffect(() => {
    const myRole: 'sender' | 'carrier' | null =
      user && parties.senderId === user.id
        ? 'sender'
        : user && parties.carrierId === user.id
        ? 'carrier'
        : null
    if (!myRole) return

    for (const msg of messages) {
      if (!msg.is_e2e || decrypted[msg.id] !== undefined) continue
      if (!msg.ciphertext_b64 || !msg.nonce_b64 || !msg.read_packages) continue
      const entry = msg.read_packages[myRole]
      if (!entry || !msg.nostr_pubkey) continue
      // T3.12 pt.2c — a re-wrapped envelope names its own sender; a legacy one
      // was addressed from the message author.
      const { ct, senderPubkey } = envelopeParts(entry, msg.nostr_pubkey)
      decryptE2E(msg.ciphertext_b64, msg.nonce_b64, ct, senderPubkey)
        .then((plaintext) =>
          setDecrypted((prev) => ({ ...prev, [msg.id]: plaintext })),
        )
        .catch(() => {
          setDecrypted((prev) => ({ ...prev, [msg.id]: '' }))
        })
    }
  }, [messages, parties, user, decrypted])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dealId || !text.trim()) return
    setSending(true)
    setError('')
    try {
      const { data } = await createMessage(
        dealId,
        text.trim(),
        false,
        parties.e2e ?? undefined,
      )
      setMessages((prev) => [...prev, data])
      setText('')
    } catch {
      setError(t('chat.sendFailed'))
    } finally {
      setSending(false)
    }
  }

  const renderMessage = (msg: VaultMessage) => {
    const att = msg.attachments[0]
    return (
      <div key={msg.id} className="space-y-1">
        <div className="flex items-center gap-2">
          {att && (
            <span className="text-xs font-mono text-navy/30 bg-navy/5 px-1.5 py-0.5 rounded">
              {t(KIND_KEY[att.kind]) ?? att.kind}
            </span>
          )}
          {msg.is_system && (
            <span className="text-xs font-mono text-cyan bg-cyan/5 px-1.5 py-0.5 rounded">
              {t('admin.systemMessage')}
            </span>
          )}
          <MonoText className="text-xs text-navy/30 ml-auto">
            {prefs.time(msg.created_at)}
          </MonoText>
        </div>

        {att && att.url && (
          <button
            type="button"
            onClick={() => setPreview({ url: att.url!, alt: t(KIND_KEY[att.kind]) ?? att.kind })}
            className="rounded-field overflow-hidden border border-navy/10 max-w-xs cursor-zoom-in hover:border-cyan/40 transition-colors block"
            aria-label={t("chat.openFullscreen") as string}
          >
            <img
              src={att.url}
              alt={t(KIND_KEY[att.kind]) ?? att.kind}
              className="w-full object-cover max-h-48"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
          </button>
        )}

        {(() => {
          const shown = msg.is_e2e ? decrypted[msg.id] : msg.text
          if (msg.card_kind && msg.card_kind !== 'address.shared'
              && !msg.card_kind.startsWith('terms.') && dealId) {
            return (
              <DealCard
                msg={msg}
                dealId={dealId}
                myRole={dealRole}
                mine={msg.sender_id === user?.id}
                onChanged={load}
              />
            )
          }
          if (msg.card_kind?.startsWith('terms.') && dealId) {
            return (
              <TermsCard
                msg={msg}
                dealId={dealId}
                myRole={dealRole}
                onChanged={load}
              />
            )
          }
          if (msg.is_e2e && shown === undefined) {
            return (
              <p className="text-sm font-body text-navy/40 italic bg-ivory rounded-field px-3 py-2 inline-block">
                🔒 {t('chat.decrypting')}
              </p>
            )
          }
          if (msg.is_e2e && shown === '') {
            return (
              <p className="text-sm font-body text-navy/40 italic bg-ivory rounded-field px-3 py-2 inline-block">
                🔒 {t('chat.needsNip07')}
              </p>
            )
          }
          if (shown && isAddressCard(msg, shown)) {
            return <AddressCard text={shown} />
          }
          if (shown) {
            return (
              <p className="text-sm font-body text-navy/80 bg-ivory rounded-field px-3 py-2 inline-block max-w-prose whitespace-pre-wrap">
                {shown}
              </p>
            )
          }
          return null
        })()}

        {att && (
          <MonoText className="text-xs text-navy/20 block">
            sha256:{att.file_hash.slice(0, 16)}…
          </MonoText>
        )}
      </div>
    )
  }

  /* T_UX.17 — the chat grows with its content instead of always claiming the
     whole viewport. A fixed height meant a two-message deal showed a screenful
     of emptiness with the composer stranded at the bottom.

     T3.11.17 (2026-09-07, owner's report) — the **page** no longer carries that
     cap. It did, and the boarding pass above the chat is expandable: opening it
     had to come out of somebody's height, and in a column of `shrink-0`
     siblings it came out of the conversation, which was squeezed to a sliver
     with its composer spilling over the card's edge. Two blocks that both want
     room must push each other, not overlap.
     So the cap moved down one level — onto the message list, which is the one
     part that can scroll without losing anything — and the page scrolls
     normally for everything else. */
  return (
    <div className="max-w-6xl flex flex-col">
      <div className="flex items-center gap-3 mb-3 sm:mb-4 shrink-0">
        {/* T3.11.26 — back to the panel, not to a deal card. It used to point at
           `/deals/:id`, which now redirects here: the link would have been a
           loop back onto the screen it is drawn on. The card itself is below,
           folded. */}
        <Link
          to="/dashboard"
          className="text-xs font-body text-navy/40 hover:text-navy transition-colors"
        >
          ← {t('nav.dashboard')}
        </Link>
        <h1 className="font-display font-bold text-xl text-navy">DealVault</h1>
        {/* T3.11.24 — the recipient is chosen, not typed. The button used to
            mint a link and copy it silently, which answered only one of the
            three ways a sender knows their recipient: from contacts, by public
            key, or — for somebody not on the platform — by a link. The picker
            holds all three and keeps them distinct. */}
        {user && parties.senderId === user.id && dealId && (
          <button
            type="button"
            onClick={() => setRecipientOpen(true)}
            className="ml-auto text-xs font-display font-medium border border-cyan/40 text-cyan px-3 py-1.5 rounded-field hover:bg-cyan/10"
          >
            {t('recipient.inviteButton')}
          </button>
        )}
      </div>

      {/* T3.11.27 — the deal card replaced the boarding pass (owner's decision
          2026-09-07). Collapsed it is the header: route, date, price, number,
          who is who. Expanded it is the agreement — four sections the two sides
          negotiate.

          **Open while it is not confirmed by both**, because agreeing it *is*
          the first stage, and a collapsed card there would have been an empty
          screen with a chat beside it. Once confirmed it folds away on its own:
          from then on the screen is about the parcel, not about the paperwork.

          What was left of the old boarding pass — the verification request and
          the dispute button — moved under it rather than disappearing: they
          belong to the deal as a whole rather than to any one stage. */}
      {deal && (
        <div className="mb-3 sm:mb-4 shrink-0">
          <DealAgreementCard
            deal={deal}
            terms={terms}
            open={cardOpen}
            onToggle={() => setCardOpen((v) => !v)}
          />
        </div>
      )}

      <details className="mb-3 sm:mb-4 shrink-0 rounded-field border border-navy/10 bg-white">
        <summary className="cursor-pointer px-3 py-2 text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
          {t('deals.moreAboutDeal')}
        </summary>
        <div className="px-3 pb-3">
          <DealPage embedded />
        </div>
      </details>

      {/* T3.11.17 — the deal on the left, the conversation on the right
          (owner's decision 2026-09-07, 60/40). They are two different readings
          of the same thing: what is happening, and what was said about it. On a
          phone the split becomes a stack — stage first, chat under it — because
          the stage is what the person came to act on. */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 items-start">
        <section className="lg:col-span-3 bg-white rounded-card border border-navy/10 p-4">
          {dealId && (
            <DealStages
              dealId={dealId}
              status={dealStatus}
              myRole={dealRole}
              terms={terms}
              /* T3.11.27 — «Форма на доске остаётся как есть, карточка
                 подставляется заполненной из неё». The deal already carries
                 what the sender typed on the board; passing it down is what
                 stops the first stage asking for it a second time. */
              deal={deal}
              onDone={load}
              onMessage={(msg) => setMessages((prev) => [...prev, msg])}
            />
          )}
        </section>

        <div className="lg:col-span-2 flex flex-col">
      <div className="bg-navy/5 rounded-field px-3 py-2 sm:px-4 sm:py-2.5 mb-3 sm:mb-4 shrink-0 flex items-center gap-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan"></span>
        <MonoText className="text-xs text-navy/60">{t('chat.immutable')}</MonoText>
      </div>

      {messages.some((m) => m.is_system && (m.text ?? '').includes('Arbiter')) && (
        <div className="bg-danger/5 border border-danger/30 rounded-field px-3 py-2 mb-3 shrink-0">
          <p className="text-xs font-body text-danger">
            ⚖️ {t('chat.arbiterOpened')}
          </p>
        </div>
      )}

      <div className="bg-white rounded-card border border-navy/10 overflow-hidden flex flex-col">
        {/* The one element with a height of its own: messages scroll, so a long
            conversation costs a scrollbar rather than a page nobody can reach
            the end of. `min-h` keeps a two-message deal from collapsing into a
            strip; everything else on this screen sizes to its content. */}
        <div className="min-h-[16rem] max-h-[55vh] overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="text-center py-8">
              <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm font-body text-navy/30">{t('chat.empty')}</p>
            </div>
          ) : (
            messages.map(renderMessage)
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="border-t border-amber/30 bg-amber/5 px-4 py-2">
            <p className="text-xs font-mono text-amber">{error}</p>
          </div>
        )}

        {notice && (
          <div className="border-t border-success/30 bg-success/5 px-4 py-2">
            <p className="text-xs font-mono text-success">{notice}</p>
          </div>
        )}

        <div className="border-t border-navy/10 p-3 sm:p-4 space-y-2 sm:space-y-3 shrink-0">
          {/* T3.11.17 — what is left in the conversation is what belongs to a
              conversation: a message, a file, an address. The photograph of a
              step and the step's own actions moved to the stage on the left,
              where the step is — including the kind selector, which asked at
              the moment somebody is holding a parcel and a phone a question
              with exactly one answer. */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setError('')
                setShareOpen(true)
              }}
              disabled={sending || !dealId}
              className="border border-cyan/40 text-cyan rounded-field px-3 py-2 min-h-[2.5rem] text-xs font-body hover:bg-cyan/10 transition-colors disabled:opacity-40"
            >
              📍 {t('chat.shareAddress.button')}
            </button>
            {/* T3.11.25 — a document this account has sent before is attached
                from the safe in one action, and the deal records that as its own
                event with the original date rather than as a fresh provision. */}
            <button
              type="button"
              onClick={() => {
                setError('')
                setSafeOpen(true)
              }}
              disabled={sending || !dealId}
              className="border border-navy/20 text-navy/60 rounded-field px-3 py-2 min-h-[2.5rem] text-xs font-body hover:border-cyan transition-colors disabled:opacity-40"
            >
              🗄 {t('safe.button')}
            </button>
          </div>
          <form onSubmit={handleSend} className="flex gap-2">
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("chat.placeholder") as string}
              className="flex-1 border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending || !text.trim()}
              className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
            >
              {sending ? '…' : t('chat.send')}
            </button>
          </form>
        </div>
        </div>
        </div>
      </div>

      {preview && (
        <ImageLightbox
          src={preview.url}
          alt={preview.alt}
          onClose={() => setPreview(null)}
        />
      )}

      <ShareAddressModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        onShare={async (addressId) => {
          if (!dealId) return
          const { data } = await shareAddressInVault(dealId, addressId)
          setMessages((prev) => [...prev, data])
        }}
      />

      {dealId && (
        <SafeFilePicker
          open={safeOpen}
          onClose={() => setSafeOpen(false)}
          onPick={async (fileId) => {
            const msg = await attachExistingFile(dealId, fileId)
            setMessages((prev) => [...prev, msg])
          }}
        />
      )}

      {dealId && (
        <RecipientModal
          open={recipientOpen}
          dealId={dealId}
          onClose={() => setRecipientOpen(false)}
          /* T3.11.24 — the participant list is what proves it happened, so the
             page reloads its messages and the confirmation is one line above
             the composer rather than an alert nobody can re-read. */
          onAttached={(name) => setNotice(t('recipient.attached', { name: name ?? '' }))}
        />
      )}
    </div>
  )
}
