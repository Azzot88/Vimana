interface MonoTextProps {
  children: React.ReactNode
  className?: string
}

export default function MonoText({ children, className = '' }: MonoTextProps) {
  return (
    <span className={`font-mono ${className}`}>
      {children}
    </span>
  )
}
