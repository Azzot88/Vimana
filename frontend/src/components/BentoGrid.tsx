import type { ReactNode } from 'react'
import { useBentoLayout } from '../hooks/useBentoLayout'

interface Props {
  children: ReactNode
  className?: string
  /** Override — force a specific column count regardless of layout hook.
   *  Useful for compact areas where a single-column look is intentional. */
  force?: 1 | 2
}

/** T_UX.1 — Bento-контейнер. Все Bento-места проходят через него.
 *
 *  desktop/tablet → 2 колонки, phone (даже landscape) → 1 колонка.
 *  См. `useBentoLayout` и `PRD/DESIGNGUIDELINES.md §5` для правила.
 */
export default function BentoGrid({ children, className = '', force }: Props) {
  const layout = useBentoLayout()
  const cols = force ?? (layout === 'phone' ? 1 : 2)
  const gridClass = cols === 1 ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'
  return (
    <div className={`grid ${gridClass} gap-4 ${className}`}>
      {children}
    </div>
  )
}
