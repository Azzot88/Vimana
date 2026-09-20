import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * T_UX.28 п.4 — «Можно прикреплять несколько фото сразу. Нужен красивый выбор
 * нескольких фото» (owner, 2026-09-19).
 *
 * The bare `<input type="file" multiple>` it replaces had two faults, and the
 * second is the one that mattered. It showed «3 файла» and nothing else, so
 * nobody could tell *which* three — and picking again **replaced** the whole
 * selection instead of adding to it, which is exactly wrong for the act this
 * form is about: photographs of a parcel are taken one at a time, from
 * different sides, and often from two different places in the phone's gallery.
 *
 * So: thumbnails, add rather than replace, and each picture removable on its
 * own. The count stays, because at the moment of a handover «сколько я уже
 * снял» is the question being asked.
 *
 * Object URLs are revoked when the list changes — a preview that outlives its
 * file is a leak, and in a form somebody keeps open on a slow connection it is
 * a growing one.
 *
 * Functions (PROJECT §6.2a):
 * - `PhotoPicker({ value, onChange, label, hint, optional })` — default export.
 *   Called by: `components/CardActions`.
 */
interface Props {
  value: File[]
  onChange: (files: File[]) => void
  /** What this pile of pictures is: «Фото передачи», «Селфи с отправителем». */
  label: string
  /** What to photograph. Above the picker, because it is about the act. */
  hint?: string
  optional?: boolean
}

export default function PhotoPicker({
  value,
  onChange,
  label,
  hint,
  optional = false,
}: Props) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const [previews, setPreviews] = useState<string[]>([])

  useEffect(() => {
    // `createObjectURL` is absent in some test environments and can throw on a
    // file the browser will not read; a missing thumbnail must not take the
    // form down with it, so the name carries the picture instead.
    const urls = value.map((file) => {
      try {
        return URL.createObjectURL(file)
      } catch {
        return ''
      }
    })
    setPreviews(urls)
    return () => {
      for (const url of urls) {
        if (!url) continue
        try {
          URL.revokeObjectURL(url)
        } catch {
          /* nothing to revoke */
        }
      }
    }
  }, [value])

  const add = (chosen: FileList | null) => {
    if (!chosen || chosen.length === 0) return
    // Added, not replaced — and the same file twice is one file: people pick a
    // picture, look at the list, and pick the same one again wondering whether
    // the first press registered.
    const known = new Set(value.map((f) => `${f.name}:${f.size}:${f.lastModified}`))
    const fresh = Array.from(chosen).filter(
      (f) => !known.has(`${f.name}:${f.size}:${f.lastModified}`),
    )
    if (fresh.length > 0) onChange([...value, ...fresh])
    // Cleared so picking the very same file again still fires `change`.
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="space-y-2">
      {hint && <p className="text-xs font-body text-navy/60">{hint}</p>}
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-body text-navy/40">
          {label}
          {optional && ` · ${t('cards.photoOptional')}`}
        </span>
        {value.length > 0 && (
          <span className="text-xs font-mono text-navy/40">
            {t('terms.photosChosen', { count: value.length })}
          </span>
        )}
      </div>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((file, index) => (
            <li
              key={`${file.name}:${file.size}:${file.lastModified}`}
              className="relative w-20 h-20 rounded-lg overflow-hidden border border-navy/10 bg-ivory"
            >
              {previews[index] ? (
                <img
                  src={previews[index]}
                  alt={file.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <span className="absolute inset-0 flex items-center justify-center p-1 text-[10px] font-body text-navy/50 text-center break-all">
                  {file.name}
                </span>
              )}
              <button
                type="button"
                onClick={() => onChange(value.filter((_, i) => i !== index))}
                aria-label={t('cards.removePhoto', { name: file.name })}
                className="absolute top-0.5 right-0.5 w-6 h-6 rounded-full bg-navy/70 text-ivory text-xs leading-none hover:bg-danger transition-colors"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="px-3 py-2 min-h-[2.75rem] rounded-field border border-navy/15 text-sm font-body text-navy/80 hover:border-cyan hover:text-cyan transition-colors"
      >
        {value.length === 0 ? t('cards.addPhotos') : t('cards.addMorePhotos')}
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        /* Every picture: what is acceptable is decided by the bytes,
           server-side. A narrow list here hides files the server takes and
           makes a phone offering `application/octet-stream` look unpickable. */
        accept="image/*"
        onChange={(e) => add(e.target.files)}
        className="hidden"
        data-testid="photo-input"
      />
    </div>
  )
}
