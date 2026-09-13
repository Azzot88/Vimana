import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  listInquiryMessages,
  listMyInquiries,
  postInquiryMessage,
  shareAddressInInquiry,
  type Inquiry,
  type InquiryMessage,
} from '../api/inquiry'
import { listDeals, type Deal } from '../api/deals'
import { useAuthStore } from '../stores/auth'
import { usePrefs } from '../hooks/usePrefs'
import { useLiveBeat } from '../hooks/useLiveBeat'
import AddressCard, { isAddressMessage } from '../components/AddressCard'
import ShareAddressModal from '../components/ShareAddressModal'
import DealSummaryCard from '../components/DealSummaryCard'
import MonoText from '../components/MonoText'

/** T3.11.23 — the outer chat: one per person, forever, with the deals nested
 *  inside it.
 *
 *  Owner's model 2026-09-07: «У нас есть общий чат с человеком… Сделка это чат
 *  вложенный в чат», and «зайти в него можно только через контакт человека».
 *  So this screen has **no link upward from a deal** — the vault does not offer
 *  one, on purpose. A message about a shipment that lives outside the record of
 *  that shipment is a message the record does not have; the friction is the
 *  feature.
 *
 *  Closed deals stay here as cards you can still open. That is the difference
 *  between a chat and a thread of the day: the conversation with a person is
 *  the place their finished deliveries remain findable.
 *
 *  Functions (PROJECT §6.2a):
 *  - `ChatPage()` — default export. Called by: the `/chats/:chatId` route.
 */
export default function ChatPage() {
  const { chatId = '' } = useParams()
  const { t, i18n } = useTranslation()
  const prefs = usePrefs()
  const user = useAuthStore((s) => s.user)

  const [chat, setChat] = useState<Inquiry | null>(null)
  const [messages, setMessages] = useState<InquiryMessage[]>([])
  const [deals, setDeals] = useState<Deal[]>([])
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [shareOpen, setShareOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        /* Three requests, and the first of them is the chat list rather than a
           chat endpoint: the list already returns the counterparty's name and
           the deal count in one batched query, and an endpoint that returned
           the same for one row would be a second way to ask the same
           question. */
        const [chats, page, dealPage] = await Promise.all([
          listMyInquiries(),
          listInquiryMessages(chatId, { limit: 100 }),
          listDeals({ chat_id: chatId, limit: 50 }),
        ])
        if (cancelled) return
        setChat(chats.data.find((c) => c.id === chatId) ?? null)
        setMessages(page.data.items)
        setDeals(dealPage.data.items)
      } catch {
        if (!cancelled) setError(t('inquiry.loadError'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [chatId, t])

  /* T3.11.27 — the same beat as the deal screen (owner, 2026-09-12).
   *
   * This screen loaded once and never again: the other person's reply simply did
   * not arrive until somebody reloaded, and neither did the status of a deal
   * nested in the conversation — which is how «сделка закрылась» first reached
   * one side and not the other.
   *
   * Deliberately **not** the whole `load`: that one sets `loading`, which would
   * blank a conversation somebody is reading every ten seconds. The lists are
   * replaced only when they differ, so an unchanged poll touches no state at all
   * — and the scroll-to-bottom below, which follows `messages.length`, stays put
   * instead of yanking a person out of their own history.
   *
   * A failed beat says nothing. The screen already has its content; an error
   * strip over working text would report the network, not the conversation.
   */
  const refresh = useCallback(async () => {
    try {
      const [page, dealPage] = await Promise.all([
        listInquiryMessages(chatId, { limit: 100 }),
        listDeals({ chat_id: chatId, limit: 50 }),
      ])
      setMessages((prev) =>
        prev.length === page.data.items.length &&
        prev.every((m, i) => m.id === page.data.items[i].id)
          ? prev
          : page.data.items,
      )
      /* Status, not just identity: a deal moving from «в пути» to «закрыта» is
         exactly the change this screen exists to show, and its id does not
         change when it happens. */
      setDeals((prev) =>
        prev.length === dealPage.data.items.length &&
        prev.every(
          (d, i) =>
            d.id === dealPage.data.items[i].id &&
            d.status === dealPage.data.items[i].status,
        )
          ? prev
          : dealPage.data.items,
      )
    } catch {
      /* silence is the correct report here — see above */
    }
  }, [chatId])

  useLiveBeat(refresh, Boolean(chatId))

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const send = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const clean = text.trim()
      if (!clean) return
      setSending(true)
      setError('')
      try {
        const { data: msg } = await postInquiryMessage(chatId, clean)
        setMessages((prev) => [...prev, msg])
        setText('')
      } catch {
        setError(t('inquiry.sendError'))
      } finally {
        setSending(false)
      }
    },
    [chatId, text, t],
  )

  /** Open deals first, then the closed ones — the live conversation is what the
   *  screen is opened for, and the archive is what it is scrolled for. */
  const sorted = useMemo(() => {
    const live = deals.filter((d) => d.status !== 'closed')
    const done = deals.filter((d) => d.status === 'closed')
    return { live, done }
  }, [deals])

  const name =
    chat?.counterparty_name || chat?.carrier_id.slice(0, 8) || chatId.slice(0, 8)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">
          {t('common.loading')}
        </MonoText>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-2xl text-navy truncate">
            {t('inquiry.chatWith', { name })}
          </h1>
          <MonoText className="text-xs text-navy/40">
            {t('inquiry.encryptedNotice')}
          </MonoText>
        </div>
        <Link to="/deals" className="text-sm font-body text-cyan hover:underline">
          {t('chats.allDeals')}
        </Link>
      </header>

      {/* The deals nested in this chat. With one of them the list is a card;
          with several it is the choice the owner asked for — «должна быть
          возможность выбрать, в какой из сделок общаться» — and it only exists
          once there is something to choose between. */}
      {deals.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-display font-semibold text-sm text-navy">
            {deals.length > 1
              ? t('chats.pickDeal', { count: deals.length })
              : t('chats.theDeal')}
          </h2>
          <div className="grid gap-2">
            {sorted.live.map((deal) => (
              <DealSummaryCard key={deal.id} deal={deal} />
            ))}
          </div>
          {sorted.done.length > 0 && (
            <details className="group">
              <summary className="cursor-pointer text-xs font-body text-navy/50 hover:text-navy py-1">
                {t('chats.closedDeals', { count: sorted.done.length })}
              </summary>
              <div className="grid gap-2 mt-2">
                {sorted.done.map((deal) => (
                  <DealSummaryCard key={deal.id} deal={deal} />
                ))}
              </div>
            </details>
          )}
        </section>
      )}

      <section className="bg-white rounded-card border border-navy/10 flex flex-col min-h-[24rem]">
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 max-h-[60vh]">
          {messages.length === 0 ? (
            <p className="text-center text-sm font-body text-navy/40 py-8">
              {t('inquiry.empty')}
            </p>
          ) : (
            messages.map((m) => {
              const mine = m.sender_id === user?.id
              const isAddr = isAddressMessage(m.text)
              return (
                <div
                  key={m.id}
                  className={`flex ${mine ? 'justify-end' : 'justify-start'}`}
                >
                  {isAddr && m.text ? (
                    <div className="max-w-[85%]">
                      <AddressCard text={m.text} />
                      <MonoText className="block text-[10px] text-navy/40 mt-1 text-right">
                        {prefs.dateTime(m.created_at)}
                      </MonoText>
                    </div>
                  ) : (
                    <div
                      className={`max-w-[80%] rounded-card px-3 py-2 text-sm font-body ${
                        mine
                          ? 'bg-cyan/20 text-navy rounded-br-sm'
                          : 'bg-ivory text-navy rounded-bl-sm'
                      }`}
                    >
                      <p className="whitespace-pre-wrap break-words">{m.text}</p>
                      <MonoText className="block text-[10px] text-navy/40 mt-1">
                        {new Date(m.created_at).toLocaleTimeString(
                          i18n.language,
                          { hour: '2-digit', minute: '2-digit' },
                        )}
                      </MonoText>
                    </div>
                  )}
                </div>
              )
            })
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <MonoText className="px-4 pb-1 text-xs text-amber">{error}</MonoText>
        )}

        <div className="border-t border-navy/10 px-3 pt-2">
          <button
            type="button"
            onClick={() => {
              setError('')
              setShareOpen(true)
            }}
            disabled={sending}
            className="text-xs font-body text-cyan hover:underline disabled:opacity-40"
          >
            📍 {t('chat.shareAddress.button')}
          </button>
        </div>

        <form onSubmit={send} className="px-3 py-2 flex gap-2">
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('inquiry.placeholder') as string}
            disabled={sending}
            className="flex-1 border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !text.trim()}
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-40"
          >
            {sending ? '…' : t('inquiry.send')}
          </button>
        </form>
      </section>

      <ShareAddressModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        onShare={async (addressId) => {
          const { data: msg } = await shareAddressInInquiry(chatId, addressId)
          setMessages((prev) => [...prev, msg])
        }}
      />
    </div>
  )
}
