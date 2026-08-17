import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

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
 */
const API_DIR = join(__dirname, '..', 'api')
const CALL = /\bapi\.(get|post|patch|put|delete)\s*(?:<[^>]*>)?\s*\(\s*([`'"])([^`'"]*)\2/g

describe('api paths', () => {
  const files = readdirSync(API_DIR).filter(
    (f) => f.endsWith('.ts') && f !== 'client.ts',
  )

  it('finds the api modules to check', () => {
    expect(files.length).toBeGreaterThan(5)
  })

  for (const file of files) {
    it(`${file} prefixes every path with /api`, () => {
      const source = readFileSync(join(API_DIR, file), 'utf8')
      const offenders: string[] = []
      for (const m of source.matchAll(CALL)) {
        const path = m[3]
        // Template literals that *begin* with an expression are not decidable
        // here; none exist today, and one appearing is a reason to look rather
        // than to widen the rule silently.
        if (!path.startsWith('/api')) offenders.push(path || '<computed>')
      }
      expect(offenders, `paths without the /api prefix in ${file}`).toEqual([])
    })
  }
})
