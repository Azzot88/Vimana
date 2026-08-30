import { Fragment } from 'react'
import { Link } from 'react-router-dom'

/**
 * T3.11.05 pt.2 — where the reader is, said at the top of the page.
 *
 * The rules pages sit four levels deep in a taxonomy the reader did not choose
 * and often arrives into sideways, from a search result rather than from the
 * front page. Without a trail the corridor page is a document with no address:
 * it says what the rules are and nothing about what it is part of, and the only
 * way back out is the browser button.
 *
 * **Two things ship together here on purpose.** The visible trail, and the
 * `BreadcrumbList` structured data that tells a search engine the same thing.
 * Google renders that trail instead of a bare URL in results, so the machine
 * copy is not decoration: it is the difference between a result that reads
 * "vimana.example > Правила > Искусство" and one that reads
 * "vimana.example/rules/art/export/RU". Written from the same array, so the two
 * cannot disagree.
 *
 * The last crumb is the current page and is not a link. Linking it would be a
 * control that does nothing, and a trail whose last item is clickable teaches
 * the reader that the trail is decorative.
 */
export interface Crumb {
  label: string
  /** Absent on the last crumb: it is where the reader already is. */
  to?: string
}

export default function Breadcrumbs({ items }: { items: Crumb[] }) {
  if (items.length === 0) return null

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((crumb, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: crumb.label,
      ...(crumb.to ? { item: crumb.to } : {}),
    })),
  }

  return (
    <nav aria-label="breadcrumb" className="text-xs font-body">
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-navy/45">
        {items.map((crumb, i) => (
          <Fragment key={`${crumb.label}-${i}`}>
            {i > 0 && (
              // Decorative, so it is hidden from the reader that hears the page
              // rather than sees it: the list markup already says these are
              // steps, and a screen reader announcing "slash" between every one
              // of them is noise.
              <li aria-hidden="true" className="text-navy/25">
                /
              </li>
            )}
            <li>
              {crumb.to ? (
                <Link
                  to={crumb.to}
                  className="transition-colors hover:text-navy"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span aria-current="page" className="text-navy/70">
                  {crumb.label}
                </span>
              )}
            </li>
          </Fragment>
        ))}
      </ol>
      {/* Safe by construction rather than by escaping: the only thing that
          reaches this string is `JSON.stringify` of an object built above, and
          JSON encodes the one character that could close the tag early. */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c'),
        }}
      />
    </nav>
  )
}
