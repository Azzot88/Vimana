import { describe, expect, it } from 'vitest'

/**
 * Every request path starts with `/api`.
 *
 * The axios client has an empty `baseURL`, so a path written without the prefix
 * is not an error anywhere: it is a valid request to the SPA's own origin, nginx
 * answers it with `index.html`, and the caller receives a page of HTML where it
 * expected JSON. The screen then dies on something like `x.filter is not a
 * function`, three layers away from the missing four characters.
 *
 * Component tests cannot catch this — they mock the api module, so the URL is
 * never exercised. Hence a check on the source itself, in the same spirit as the
 * IDOR matrix on the backend: a new endpoint fails this file by the mere fact of
 * being written the wrong way.
 *
 * Sources are read through `import.meta.glob` rather than `node:fs` on purpose.
 * The same `tsc` run that type-checks this file also builds the browser bundle,
 * and it has no Node types — a test reaching for `fs` breaks the production
 * build, which is a worse outcome than the bug it was written to prevent.
 */
const SOURCES = import.meta.glob('../api/*.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const CALL = /\bapi\.(get|post|patch|put|delete)\s*(?:<[^>]*>)?\s*\(\s*([`'"])([^`'"]*)\2/g

describe('api paths', () => {
  const files = Object.entries(SOURCES).filter(
    ([path]) => !path.endsWith('client.ts'),
  )

  it('finds the api modules to check', () => {
    expect(files.length).toBeGreaterThan(5)
  })

  for (const [path, source] of files) {
    it(`${path.split('/').pop()} prefixes every path with /api`, () => {
      const offenders: string[] = []
      for (const m of source.matchAll(CALL)) {
        const url = m[3]
        // Template literals that *begin* with an expression are not decidable
        // here; none exist today, and one appearing is a reason to look rather
        // than to widen the rule silently.
        if (!url.startsWith('/api')) offenders.push(url || '<computed>')
      }
      expect(offenders, `paths without the /api prefix in ${path}`).toEqual([])
    })
  }
})
