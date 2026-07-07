import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { listMessages, createMessage, uploadAttachment, type VaultMessage } from '../api/dealvault'
import MonoText from '../components/MonoText'

export default function DealVaultPage() {
  const { dealId } = useParams<{ dealId: string }>()
  const [messages, setMessages] = useState<VaultMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [uploadKind, setUploadKind] = useState<'handoff_photo' | 'receipt_photo'>('handoff_photo')
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = async () => {
    if (!dealId) return
    try {
      const { data } = await listMessages(dealId)
      setMessages(data.items)
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
    try {
      const { data } = await createMessage(dealId, { kind: 'text', body: text.trim() })
      setMessages((prev) => [...prev, data])
      setText('')
    } finally {
      setSending(false)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !dealId) return
    setSending(true)
    try {
      const { data } = await uploadAttachment(dealId, file, uploadKind)
      setMessages((prev) => [...prev, data])
    } finally {
      setSending(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const kindLabel = (kind: VaultMessage['kind']) => {
    const map: Record<string, string> = {
      text: 'Сообщение',
      handoff_photo: 'Фото передачи',
      receipt_photo: 'Фото получения',
      system: 'Система',
    }
    return map[kind] ?? kind
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
            messages.map((msg) => (
              <div key={msg.id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-body font-medium text-navy">{msg.sender_name}</span>
                  <span className="text-xs font-mono text-navy/30 bg-navy/5 px-1.5 py-0.5 rounded">
                    {kindLabel(msg.kind)}
                  </span>
                  <MonoText className="text-xs text-navy/30 ml-auto">
                    {new Date(msg.created_at).toLocaleTimeString('ru-RU')}
                  </MonoText>
                </div>
                {msg.attachment_url ? (
                  <div className="rounded-lg overflow-hidden border border-navy/10 max-w-xs">
                    <img
                      src={msg.attachment_url}
                      alt={kindLabel(msg.kind)}
                      className="w-full object-cover max-h-48"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  </div>
                ) : (
                  <p className="text-sm font-body text-navy/80 bg-ivory rounded-lg px-3 py-2 inline-block max-w-prose">
                    {msg.body}
                  </p>
                )}
                <MonoText className="text-xs text-navy/20 block">
                  sha256:{msg.sha256?.slice(0, 16)}...
                </MonoText>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-navy/10 p-3 sm:p-4 space-y-2 sm:space-y-3 shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={uploadKind}
              onChange={(e) => setUploadKind(e.target.value as typeof uploadKind)}
              className="text-xs font-mono border border-navy/20 rounded-lg px-2 py-2 min-h-[2.5rem] text-navy focus:outline-none focus:border-cyan"
            >
              <option value="handoff_photo">Фото передачи</option>
              <option value="receipt_photo">Фото получения</option>
            </select>
            <label className="cursor-pointer border border-navy/20 rounded-lg px-3 py-2 min-h-[2.5rem] text-xs font-body text-navy/60 hover:border-cyan transition-colors flex items-center">
              Загрузить фото
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
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
    </div>
  )
}
