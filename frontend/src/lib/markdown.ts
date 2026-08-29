import MarkdownIt from 'markdown-it'

/**
 * T3.11.03 pt.3 — the one renderer for rule text, used by the public page, by
 * the editor's preview, and by the prerender step in Node.
 *
 * **`html: false` is the security decision, and it is stronger than sanitising.**
 * Sanitising cleans markup that already exists; this stops it from becoming
 * markup at all. `<script>` in a rule's body stays the literal text
 * `<script>` at every stage — in the database, in the `.md` download, in the
 * MCP answer and on the page. There is no stage at which it is markup waiting
 * to be cleaned, which is a different claim from "we clean it well".
 *
 * `linkify` stays off. Auto-linking bare URLs is a convenience that quietly
 * turns any string containing a dot into a link, and rule text is full of
 * citations like `9 CFR 2.150`. Editors write links deliberately.
 *
 * `markdown-it` validates link targets by default and refuses `javascript:`,
 * `vbscript:` and `data:` — that guard is why this is configured rather than
 * replaced with a hand-rolled two-line converter.
 *
 * Functions (PROJECT §6.2a):
 * - `renderMarkdown(src)` — Markdown to HTML. Called by: `pages/RulesPage`,
 *   `components/RuleSectionCard` (preview), `entry-ssr` through the page.
 */
const md = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: false,
  typographer: false,
})

const defaultLinkOpen =
  md.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  // Every link in a rule points outward — at an authority's site, at a PDF of
  // a regulation. `noopener` because a new tab must not get a handle on this
  // one; `nofollow` because a directory of corridors should not hand its
  // standing to whatever a corpus happens to cite.
  tokens[idx].attrSet('rel', 'nofollow noopener')
  tokens[idx].attrSet('target', '_blank')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(src: string): string {
  return md.render(src ?? '')
}
