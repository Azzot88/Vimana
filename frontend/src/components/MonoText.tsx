interface MonoTextProps {
  children: React.ReactNode
  className?: string
  /** T_UX.28 — the exact stamp behind a relative one («11 минут назад» hovers
   *  to «16.09.2026 14:12»). Native `title`, so it reaches the accessibility
   *  tree and needs no tooltip of our own. */
  title?: string
}

export default function MonoText({ children, className = '', title }: MonoTextProps) {
  return (
    <span className={`font-mono ${className}`} title={title}>
      {children}
    </span>
  )
}
