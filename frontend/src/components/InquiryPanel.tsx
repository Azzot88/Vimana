import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  listInquiryMessages,
  openInquiry,
  postInquiryMessage,
  type InquiryMessage,
} from '../api/inquiry'
import { useAuthStore } from '../stores/auth'

interface Props {
  tripId: string
  carrierName: string
  onClose: () => void
}

export default function InquiryPanel({ tripId, carrierName, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [inquiryId, setInquiryId] = useState<string | null>(null)
  const [messages, setMessages] = useState<InquiryMessage[]>([])
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    const bootstrap = async () => {
      setLoading(true)
      setError('')
      try {
        const { data: inq } = await openInquiry(tripId)
        if (cancelled) return
        setInquiryId(inq.id)
        const { data: page } = await listInquiryMessages(inq.id, { limit: 100 })
        if (cancelled) return
        setMessages(page.items)
      } catch {
        if (!cancelled) setError(t('inquiry.loadError'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [tripId, t])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    const clean = text.trim()
    if (!clean || !inquiryId) return
    setSending(true)
    setError('')
    try {
      const { data: msg } = await postInquiryMessage(inquiryId, clean)
      setMessages((prev) => [...prev, msg])
      setText('')
    } catch {
      setError(t('inquiry.sendError'))
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <div
        onClick={onClose}
        className="fixed inset-0 bg-navy/40 backdrop-blur-sm z-40 md:hidden"
      />
      <aside
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[420px] md:w-[380px] bg-white shadow-2xl flex flex-col border-l border-navy/10"
        role="dialog"
        aria-label={t('inquiry.panelLabel')}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy/10 bg-ivory">
          <div>
            <p className="font-display font-semibold text-navy text-sm">
              {t('inquiry.chatWith', { name: carrierName })}
            </p>
            <p className="text-xs font-mono text-navy/40 mt-0.5">
              {t('inquiry.encryptedNotice')}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label={t('common.close')}
            className="text-navy/50 hover:text-navy text-xl leading-none px-2"
          >
            ×
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <p className="text-center text-sm font-body text-navy/40 py-8">
              {t('common.loading')}
            </p>
          ) : messages.length === 0 ? (
            <p className="text-center text-sm font-body text-navy/40 py-8">
              {t('inquiry.empty')}
            </p>
          ) : (
            messages.map((m) => {
              const mine = m.sender_id === user?.id
              return (
                <div
                  key={m.id}
                  className={`flex ${mine ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm font-body ${
                      mine
                        ? 'bg-cyan/20 text-navy rounded-br-sm'
                        : 'bg-ivory text-navy rounded-bl-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap break-words">{m.text}</p>
                    <p className="text-[10px] font-mono text-navy/40 mt-1">
                      {new Date(m.created_at).toLocaleTimeString(i18n.language, {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                </div>
              )
            })
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <p className="px-4 pb-1 text-xs font-mono text-orange-600">{error}</p>
        )}

        <form
          onSubmit={handleSend}
          className="border-t border-navy/10 px-3 py-2 flex gap-2"
        >
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t('inquiry.placeholder') as string}
            disabled={sending || !inquiryId}
            className="flex-1 border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !text.trim() || !inquiryId}
            className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-40"
          >
            {sending ? '…' : t('inquiry.send')}
          </button>
        </form>
      </aside>
    </>
  )
}
