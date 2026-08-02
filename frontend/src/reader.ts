/**
 * T3.24 — the `.dvlt` reader.
 *
 * The point of this file is a claim the product makes and must be able to
 * keep: **your Identity Vault opens without us.** A reader that needed our API
 * would make the claim circular, so this page has no API client, no auth and
 * no imports from the app — only the sealing primitives it shares with the
 * profile, which are the same NIP-49 the rest of the Nostr world implements.
 *
 * What it verifies is stated plainly on the page and nothing more: the file
 * decrypts under the given passphrase, and the key inside derives the public
 * key written next to it. That second check matters — a container carrying
 * someone else's npub beside your key would otherwise look perfectly fine.
 *
 * `type: "deal"` is recognised and refused for now: deal export (`.dvlt` of a
 * vault) is deliberately deferred (`D-DVLT-PROTOCOL` п.6), and a reader that
 * pretended to handle a file nobody can produce yet would be the same kind of
 * overclaim §9.1 forbids.
 */
import {
  npubBech32,
  npubFromNsec,
  openIdentityVault,
  type IdentityVaultFile,
} from './lib/identity'

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T

const fileInput = $<HTMLInputElement>('file')
const passInput = $<HTMLInputElement>('pass')
const openBtn = $<HTMLButtonElement>('open')
const revealBtn = $<HTMLButtonElement>('reveal')
const errorBox = $<HTMLParagraphElement>('error')
const result = $<HTMLElement>('result')
const nsecRow = $<HTMLElement>('nsecRow')

let nsecHex = ''
let ncryptsec = ''

/**
 * Copy, with a fallback that matters here more than usual: saved to disk the
 * page runs from `file://`, where the clipboard API is often unavailable. In
 * that case the text is selected instead, so Ctrl+C still works — an offline
 * copy of this page must not be the broken one.
 */
async function copy(text: string, source: HTMLElement): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    const note = $('copied')
    note.classList.remove('hidden')
    setTimeout(() => note.classList.add('hidden'), 1500)
  } catch {
    const range = document.createRange()
    range.selectNodeContents(source)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
  }
}

function fail(message: string): void {
  errorBox.textContent = message
  errorBox.classList.remove('hidden')
  result.classList.add('hidden')
}

function parseVault(text: string): IdentityVaultFile {
  // Typed as an open record on purpose: this is a file from disk, not our own
  // object, and narrowing it to the interface before checking would let
  // TypeScript "prove" things about bytes nobody has validated.
  const data = JSON.parse(text) as Record<string, unknown>
  if (data.type === 'deal') {
    throw new Error(
      'This is a deal vault. Exporting deals is not built yet, so no reader can open one.',
    )
  }
  if (data.type !== 'identity') {
    throw new Error('Not a Vimana Identity Vault file.')
  }
  if (data.v !== 2) {
    throw new Error(`This file is version ${String(data.v)}; this reader knows version 2.`)
  }
  if (!data.sealed || !data.nonce || !data.kdf) {
    throw new Error('The file is missing its sealed contents.')
  }
  return data as unknown as IdentityVaultFile
}

async function handleOpen(): Promise<void> {
  errorBox.classList.add('hidden')
  result.classList.add('hidden')
  nsecRow.classList.add('hidden')
  nsecHex = ''

  const file = fileInput.files?.[0]
  if (!file) return fail('Choose a .dvlt file first.')
  if (!passInput.value) return fail('Enter the passphrase you sealed the file with.')

  openBtn.disabled = true
  openBtn.textContent = 'Opening…'
  try {
    const vault = parseVault(await file.text())
    // Wrong passphrase fails here, on the authentication tag — nothing decrypts
    // to a plausible but different value.
    const contents = openIdentityVault(vault, passInput.value)
    const derived = npubBech32(npubFromNsec(contents.nsec))
    if (derived !== contents.npub) {
      throw new Error(
        'The key inside does not match the public key stored beside it.',
      )
    }
    nsecHex = contents.nsec
    ncryptsec = contents.ncryptsec
    $('npub').textContent = contents.npub
    $('created').textContent = contents.created_at || '—'
    result.classList.remove('hidden')
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    // A decryption failure and a wrong file look the same to a user in the
    // moment, so the wording covers both without guessing which it was.
    fail(
      message.includes('Identity Vault') || message.includes('deal vault') || message.includes('version')
        ? message
        : 'Could not open it — check the passphrase, or the file is not an Identity Vault.',
    )
  } finally {
    openBtn.disabled = false
    openBtn.textContent = 'Open'
  }
}

openBtn.addEventListener('click', () => void handleOpen())
revealBtn.addEventListener('click', () => {
  if (!nsecHex) return
  $('nsec').textContent = nsecHex
  nsecRow.classList.remove('hidden')
  revealBtn.classList.add('hidden')
})

$('copyNpub').addEventListener('click', () => void copy($('npub').textContent || '', $('npub')))
$('copyNsec').addEventListener('click', () => void copy(nsecHex, $('nsec')))
// The encrypted string, not the bare key: this is the one meant to be pasted
// somewhere else, and it stays useless to whoever has not got the passphrase.
$('copyNcryptsec').addEventListener('click', () => void copy(ncryptsec, $('npub')))
