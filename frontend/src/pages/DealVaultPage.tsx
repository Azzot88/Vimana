import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  createMessage,
  listMessages,
  sendPhotoMessage,
  type AttachmentKind,
  type VaultMessage,
} from '../api/dealvault'
import ImageLightbox from '../components/ImageLightbox'
import MonoText from '../components/MonoText'

const KIND_LABEL: Record<AttachmentKind, string> = {
  handoff_photo: 'Фото передачи',
  receipt_photo: 'Фото получения',
  doc: 'Документ',
  payment_receipt: 'Чек оплаты',
}

export default function DealVaultPage() {
  const { dealId } = useParams<{ dealId: string }>()
  const [messages, setMessages] = useState<VaultMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string>('')
  const [uploadKind, setUploadKind] = useState<AttachmentKind>('handoff_photo')
  const [preview, setPreview] = useState<{ url: string; alt: string } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    if (!dealId) return
    try {
      const { data } = await listMessages(dealId, { limit: 100 })
      setMessages(data.items)
    } catch {
      setError('Не удалось загрузить сообщения')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [dealId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dealId || !text.trim()) return
    setSending(true)
    setError('')
    try {
      const { data } = await createMessage(dealId, text.trim())
      setMessages((prev) => [...prev, data])
      setText('')
    } catch {
      setError('Не удалось отправить сообщение')
    } finally {
      setSending(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !dealId) return
    setSending(true)
    setError('')
    try {
      const msg = await sendPhotoMessage(dealId, file, uploadKind)
      setMessages((prev) => [...prev, msg])
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Не удалось загрузить файл')
    } finally {
      setSending(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const renderMessage = (msg: VaultMessage) => {
    const att = msg.attachments[0]
    return (
      <div key={msg.id} className="space-y-1">
        <div className="flex items-center gap-2">
          {att && (
            <span className="text-xs font-mono text-navy/30 bg-navy/5 px-1.5 py-0.5 rounded">
              {KIND_LABEL[att.kind] ?? att.kind}
            </span>
          )}
          {msg.is_system && (
            <span className="text-xs font-mono text-cyan bg-cyan/5 px-1.5 py-0.5 rounded">
              Система
            </span>
          )}
          <MonoText className="text-xs text-navy/30 ml-auto">
            {new Date(msg.created_at).toLocaleTimeString('ru-RU')}
          </MonoText>
        </div>

        {att && att.url && (
          <button
            type="button"
            onClick={() => setPreview({ url: att.url!, alt: KIND_LABEL[att.kind] ?? att.kind })}
            className="rounded-lg overflow-hidden border border-navy/10 max-w-xs cursor-zoom-in hover:border-cyan/40 transition-colors block"
            aria-label="Открыть в полный экран"
          >
            <img
              src={att.url}
              alt={KIND_LABEL[att.kind] ?? att.kind}
              className="w-full object-cover max-h-48"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
          </button>
        )}

        {msg.text && (
          <p className="text-sm font-body text-navy/80 bg-ivory rounded-lg px-3 py-2 inline-block max-w-prose">
            {msg.text}
          </p>
        )}

        {att && (
          <MonoText className="text-xs text-navy/20 block">
            sha256:{att.file_hash.slice(0, 16)}…
          </MonoText>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-2xl flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-10rem)]">
      <div className="flex items-center gap-3 mb-3 sm:mb-4 shrink-0">
        <Link to={`/deals/${dealId}`} className="text-xs font-body text-navy/40 hover:text-navy transition-colors">
          ← Сделка
        </Link>
        <h1 className="font-display font-bold text-xl text-navy">DealVault</h1>
      </div>

      <div className="bg-navy/5 rounded-lg px-3 py-2 sm:px-4 sm:py-2.5 mb-3 sm:mb-4 shrink-0 flex items-center gap-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan"></span>
        <MonoText className="text-xs text-navy/60">Иммутабельно · SHA-256</MonoText>
      </div>

      {messages.some((m) => m.is_system && (m.text ?? '').includes('Arbiter')) && (
        <div className="bg-red-50 border border-red-300 rounded-lg px-3 py-2 mb-3 shrink-0">
          <p className="text-xs font-body text-red-700">
            ⚖️ Арбитр открыл переписку по спору. Обе стороны видят это уведомление.
          </p>
        </div>
      )}

      <div className="flex-1 bg-white rounded-xl border border-navy/10 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            <div className="text-center py-8">
              <MonoText className="text-navy/40 text-sm">Загрузка...</MonoText>
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm font-body text-navy/30">Нет сообщений</p>
            </div>
          ) : (
            messages.map(renderMessage)
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="border-t border-orange-200 bg-orange-50 px-4 py-2">
            <p className="text-xs font-mono text-orange-700">{error}</p>
          </div>
        )}

        <div className="border-t border-navy/10 p-3 sm:p-4 space-y-2 sm:space-y-3 shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={uploadKind}
              onChange={(e) => setUploadKind(e.target.value as AttachmentKind)}
              className="text-xs font-mono border border-navy/20 rounded-lg px-2 py-2 min-h-[2.5rem] text-navy focus:outline-none focus:border-cyan"
            >
              <option value="handoff_photo">Фото передачи</option>
              <option value="receipt_photo">Фото получения</option>
              <option value="doc">Документ</option>
              <option value="payment_receipt">Чек оплаты</option>
            </select>
            <label className="cursor-pointer border border-navy/20 rounded-lg px-3 py-2 min-h-[2.5rem] text-xs font-body text-navy/60 hover:border-cyan transition-colors flex items-center">
              {sending ? 'Отправка…' : 'Загрузить фото'}
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
                onChange={handleUpload}
                className="hidden"
                disabled={sending}
              />
            </label>
          </div>
          <form onSubmit={handleSend} className="flex gap-2">
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Сообщение..."
              className="flex-1 border border-navy/20 rounded-lg px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending || !text.trim()}
              className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
            >
              {sending ? '...' : 'Отправить'}
            </button>
          </form>
        </div>
      </div>

      {preview && (
        <ImageLightbox
          src={preview.url}
          alt={preview.alt}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  )
}
