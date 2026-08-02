import { useEffect } from 'react'

interface Props {
  src: string
  alt?: string
  onClose: () => void
}

export default function ImageLightbox({ src, alt, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-modal bg-black/85 flex items-center justify-center p-4 cursor-zoom-out"
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 text-white/70 hover:text-white text-2xl leading-none w-10 h-10 rounded-full bg-black/40 hover:bg-black/60 flex items-center justify-center"
      >
        ×
      </button>
      <img
        src={src}
        alt={alt ?? ''}
        onClick={(e) => e.stopPropagation()}
        className="max-w-[95vw] max-h-[92vh] object-contain rounded-field shadow-2xl cursor-zoom-out select-none"
      />
    </div>
  )
}
