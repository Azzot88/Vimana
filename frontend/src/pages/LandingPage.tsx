import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import LanguageSwitcher from '../components/LanguageSwitcher'

const LP_CSS = `
.lp {
  --lp-bg:      #EDE8DC;
  --lp-card:    #FFFFFF;
  --lp-warm:    #FBF8F2;
  --lp-sky-bg:  #EEF5FA;
  --lp-gold-bg: #FDF8ED;
  --lp-navy:    #1C3252;
  --lp-navym:   #2D4D70;
  --lp-gold:    #A86E08;
  --lp-goldw:   #C98E18;
  --lp-sky:     #3D80B8;
  --lp-amber:   #C8621A;
  --lp-success: #1D6B40;
  --lp-mid:     #4D6278;
  --lp-muted:   #7A8E9E;
  --lp-border:  rgba(28,50,82,0.10);
  --lp-shadow:  0 1px 10px rgba(28,50,82,0.08);
  background: var(--lp-bg);
  color: var(--lp-navy);
  min-height: 100vh;
  overflow-x: hidden;
}

/* NAV */
.lp-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 48px;
  border-bottom: 1px solid var(--lp-border);
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(20px);
  background: rgba(237,232,220,0.90);
}
.lp-wordmark { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:19px; letter-spacing:-0.4px; color:var(--lp-navy); text-decoration:none; }
.lp-wordmark span { color:var(--lp-amber); }
.lp-nav-tag { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--lp-muted); letter-spacing:0.08em; }
.lp-cta { background:var(--lp-navy); color:#F8F7F4; font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:13px; padding:9px 18px; border-radius:8px; border:none; cursor:pointer; text-decoration:none; transition:background 0.15s; }
.lp-cta:hover { background:var(--lp-navym); }

/* HERO */
.lp-hero { max-width:1200px; margin:0 auto; padding:72px 48px 40px; }
.lp-eyebrow { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--lp-amber); letter-spacing:0.18em; text-transform:uppercase; margin-bottom:20px; }
.lp-h1 { font-family:'Space Grotesk',sans-serif; font-size:clamp(48px,6.5vw,84px); font-weight:700; line-height:1.0; letter-spacing:-2.5px; color:var(--lp-navy); margin-bottom:22px; }
.lp-h1 em { font-style:normal; color:var(--lp-sky); }
.lp-sub { font-size:17px; line-height:1.65; color:var(--lp-mid); max-width:540px; margin-bottom:40px; }

/* BENTO GRID */
.lp-bento { max-width:1200px; margin:0 auto; padding:0 48px 80px; display:grid; grid-template-columns:repeat(12,1fr); grid-auto-rows:90px; gap:10px; }

.lp-cell { background:var(--lp-card); border:1px solid var(--lp-border); border-radius:20px; padding:26px; overflow:hidden; position:relative; transition:box-shadow 0.18s,transform 0.18s; box-shadow:var(--lp-shadow); }
.lp-cell:hover { box-shadow:0 4px 20px rgba(28,50,82,0.12); transform:translateY(-2px); }

.lp-s74 { grid-column:span 7; grid-row:span 4; }
.lp-s54 { grid-column:span 5; grid-row:span 4; }
.lp-s73 { grid-column:span 7; grid-row:span 3; }
.lp-s53 { grid-column:span 5; grid-row:span 3; }
.lp-s43 { grid-column:span 4; grid-row:span 3; }
.lp-s42 { grid-column:span 4; grid-row:span 2; }
.lp-s52 { grid-column:span 5; grid-row:span 2; }
.lp-s72 { grid-column:span 7; grid-row:span 2; }

.lp-clabel { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.12em; text-transform:uppercase; color:var(--lp-muted); margin-bottom:6px; }
.lp-ctitle { font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:15px; color:var(--lp-navy); }

/* ROUTE CELL */
.lp-route::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,var(--lp-amber),var(--lp-sky)); border-radius:20px 20px 0 0; }
.lp-iata { font-family:'IBM Plex Mono',monospace; font-size:46px; font-weight:500; color:var(--lp-navy); letter-spacing:-1px; line-height:1; }
.lp-iata-city { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-muted); margin-top:3px; }
.lp-route-row { display:flex; align-items:center; gap:12px; margin:14px 0 18px; }
.lp-arrow { flex:1; display:flex; align-items:center; justify-content:center; color:var(--lp-amber); font-size:20px; }
.lp-arrow::before,.lp-arrow::after { content:''; flex:1; height:1px; background:linear-gradient(90deg,var(--lp-amber),rgba(200,98,26,0.08)); }
.lp-arrow::after { background:linear-gradient(90deg,rgba(200,98,26,0.08),var(--lp-amber)); }
.lp-rmeta-row { display:flex; gap:24px; }
.lp-rmeta label { font-family:'IBM Plex Mono',monospace; font-size:9px; color:var(--lp-muted); letter-spacing:0.1em; text-transform:uppercase; display:block; margin-bottom:2px; }
.lp-rmeta span { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--lp-navy); }
.lp-tags { display:flex; gap:6px; flex-wrap:wrap; margin-top:16px; }
.lp-tag { font-family:'IBM Plex Mono',monospace; font-size:10px; padding:3px 10px; border-radius:100px; background:rgba(61,128,184,0.08); border:1px solid rgba(61,128,184,0.18); color:var(--lp-sky); }

/* VAULT */
.lp-vault { background:var(--lp-sky-bg)!important; border-color:rgba(61,128,184,0.15)!important; }
.lp-vrow { display:flex; align-items:center; gap:8px; background:rgba(255,255,255,0.75); border-radius:8px; padding:7px 11px; font-size:11px; margin-bottom:6px; }
.lp-vrow.lp-ok { background:rgba(29,107,64,0.06); border:1px solid rgba(29,107,64,0.15); }
.lp-vtext { flex:1; color:var(--lp-navy); }
.lp-vtime { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-sky); white-space:nowrap; }
.lp-ok .lp-vtext { color:var(--lp-success); }
.lp-ok .lp-vtime { color:var(--lp-success); }
.lp-vault-badge { font-family:'IBM Plex Mono',monospace; font-size:9px; letter-spacing:0.1em; color:var(--lp-sky); background:rgba(61,128,184,0.08); border:1px solid rgba(61,128,184,0.2); padding:4px 9px; border-radius:5px; display:inline-block; margin-top:10px; }

/* BOARDING PASS */
.lp-boarding { background:var(--lp-warm)!important; }
.lp-bp-inner { border:1.5px dashed rgba(28,50,82,0.18); border-radius:12px; padding:16px 18px; height:100%; display:flex; flex-direction:column; justify-content:space-between; }
.lp-bp-brand { font-family:'Space Grotesk',sans-serif; font-size:11px; font-weight:600; color:var(--lp-navy); letter-spacing:0.05em; }
.lp-bp-id { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-muted); }
.lp-bp-route { font-family:'IBM Plex Mono',monospace; font-size:26px; font-weight:500; color:var(--lp-navy); letter-spacing:-0.5px; margin:6px 0; }
.lp-bp-fields { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.lp-bpf label { font-family:'IBM Plex Mono',monospace; font-size:9px; color:var(--lp-muted); text-transform:uppercase; letter-spacing:0.1em; display:block; }
.lp-bpf span { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--lp-navy); font-weight:500; }
.lp-sdot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--lp-success); margin-right:4px; }

/* TRUST */
.lp-trust { background:var(--lp-gold-bg)!important; border-color:rgba(168,110,8,0.12)!important; }
.lp-trust-score { font-family:'Space Grotesk',sans-serif; font-size:38px; font-weight:700; color:var(--lp-gold); line-height:1; margin:6px 0 2px; }
.lp-trust-bar { height:3px; background:rgba(168,110,8,0.1); border-radius:2px; margin:10px 0; }
.lp-trust-fill { height:100%; width:73%; background:linear-gradient(90deg,var(--lp-gold),var(--lp-sky)); border-radius:2px; }
.lp-tiers { display:flex; gap:5px; flex-wrap:wrap; }
.lp-tier { font-family:'IBM Plex Mono',monospace; font-size:9px; padding:3px 7px; border-radius:4px; border:1px solid var(--lp-border); color:var(--lp-muted); }
.lp-tier.lp-on { border-color:var(--lp-gold); color:var(--lp-gold); background:rgba(168,110,8,0.06); }

/* TAGLINE */
.lp-tagline-cell { background:var(--lp-navy)!important; border-color:transparent!important; }
.lp-tagline { font-family:'Space Grotesk',sans-serif; font-size:21px; font-weight:700; color:#F8F7F4; line-height:1.2; letter-spacing:-0.5px; margin-top:10px; }
.lp-tagline em { font-style:normal; color:var(--lp-goldw); }

/* ESCROW */
.lp-escrow { border-color:rgba(29,107,64,0.15)!important; }
.lp-esc-row { display:flex; align-items:center; gap:8px; margin:12px 0; }
.lp-epty { flex:1; text-align:center; }
.lp-eicon { width:34px; height:34px; border-radius:50%; background:rgba(28,50,82,0.05); border:1px solid var(--lp-border); margin:0 auto 5px; display:flex; align-items:center; justify-content:center; font-size:15px; }
.lp-elabel { font-family:'IBM Plex Mono',monospace; font-size:9px; color:var(--lp-muted); letter-spacing:0.05em; }

/* NETWORK */
.lp-net-canvas { position:relative; height:86px; margin:10px 0 4px; }
.lp-nnode { position:absolute; width:28px; height:28px; border-radius:50%; background:rgba(61,128,184,0.10); border:1px solid rgba(61,128,184,0.25); display:flex; align-items:center; justify-content:center; font-size:12px; }
.lp-nline { position:absolute; height:1px; background:rgba(61,128,184,0.2); transform-origin:left center; }

/* SKY BG CELL */
.lp-sky-cell { background:var(--lp-sky-bg)!important; border-color:rgba(61,128,184,0.12)!important; }
.lp-gold-cell { background:var(--lp-gold-bg)!important; border-color:rgba(168,110,8,0.15)!important; }
.lp-warm-cell { background:var(--lp-warm)!important; }

/* PROGRESS */
.lp-prow { display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--lp-border); }
.lp-prow:last-child { border-bottom:none; }
.lp-pdot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.lp-pname { font-size:12px; flex:1; }
.lp-pname.lp-dim { color:var(--lp-muted); }
.lp-pver { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-sky); }
.lp-pver.lp-dim { color:var(--lp-muted); }

/* FOOTER */
.lp-footer { border-top:1px solid var(--lp-border); padding:28px 48px; max-width:1200px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; }
.lp-fmono { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--lp-muted); }

/* MODAL OVERLAY */
.lp-overlay { position:fixed; inset:0; background:rgba(28,50,82,0.40); backdrop-filter:blur(8px); z-index:500; display:flex; align-items:center; justify-content:center; }
.lp-modal { background:var(--lp-warm); border:1px solid var(--lp-border); border-radius:24px; padding:40px; width:100%; max-width:440px; box-shadow:0 24px 64px rgba(28,50,82,0.16); position:relative; }
.lp-mclose { position:absolute; top:16px; right:18px; background:none; border:none; font-size:20px; color:var(--lp-muted); cursor:pointer; line-height:1; padding:4px; }
.lp-mclose:hover { color:var(--lp-navy); }
.lp-meyebrow { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-amber); letter-spacing:0.15em; text-transform:uppercase; margin-bottom:10px; }
.lp-mtitle { font-family:'Space Grotesk',sans-serif; font-size:26px; font-weight:700; color:var(--lp-navy); letter-spacing:-0.5px; margin-bottom:8px; }
.lp-msub { font-size:14px; color:var(--lp-mid); line-height:1.55; margin-bottom:28px; }
.lp-mfield { margin-bottom:14px; }
.lp-mfield label { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-muted); letter-spacing:0.08em; text-transform:uppercase; display:block; margin-bottom:6px; }
.lp-mfield input { width:100%; background:var(--lp-card); border:1px solid var(--lp-border); border-radius:10px; padding:12px 14px; font-family:Inter,sans-serif; font-size:14px; color:var(--lp-navy); outline:none; transition:border-color 0.15s; }
.lp-mfield input::placeholder { color:var(--lp-muted); }
.lp-mfield input:focus { border-color:var(--lp-sky); }
.lp-msubmit { width:100%; background:var(--lp-navy); color:#F8F7F4; font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:15px; padding:13px; border-radius:10px; border:none; cursor:pointer; margin-top:6px; transition:background 0.15s; }
.lp-msubmit:hover { background:var(--lp-navym); }
.lp-msubmit:disabled { opacity:0.6; cursor:not-allowed; }
.lp-mfine { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--lp-muted); text-align:center; margin-top:14px; }
.lp-msuccess { text-align:center; }
.lp-msuccess .lp-check { font-size:44px; margin-bottom:14px; }
.lp-msuccess h3 { font-family:'Space Grotesk',sans-serif; font-size:22px; font-weight:700; color:var(--lp-navy); margin-bottom:8px; }
.lp-msuccess p { font-size:14px; color:var(--lp-mid); line-height:1.55; }

/* ─── RESPONSIVE — TABLET (≤1024px): 6-column grid, bento cells regroup ─── */
@media (max-width: 1024px) {
  .lp-nav { padding: 16px 28px; }
  .lp-hero { padding: 56px 28px 32px; }
  .lp-sub { max-width: 100%; }

  .lp-bento {
    padding: 0 28px 64px;
    grid-template-columns: repeat(6, 1fr);
    grid-auto-rows: 90px;
    gap: 10px;
  }
  .lp-s74 { grid-column: span 6; grid-row: span 4; }
  .lp-s54 { grid-column: span 6; grid-row: span 4; }
  .lp-s73 { grid-column: span 6; grid-row: span 3; }
  .lp-s53 { grid-column: span 6; grid-row: span 3; }
  .lp-s72 { grid-column: span 6; grid-row: span 2; }
  .lp-s52 { grid-column: span 6; grid-row: span 2; }
  .lp-s43 { grid-column: span 3; grid-row: span 3; }
  .lp-s42 { grid-column: span 3; grid-row: span 2; }

  .lp-footer { padding: 24px 28px; }
}

/* ─── RESPONSIVE — MOBILE (≤640px): single column, auto height ─── */
@media (max-width: 640px) {
  .lp-nav { padding: 14px 18px; gap: 10px; }
  .lp-nav-tag { display: none; }

  .lp-hero { padding: 40px 18px 24px; }
  .lp-h1 { letter-spacing: -1.2px; line-height: 1.05; }
  .lp-sub { font-size: 15px; }

  .lp-bento {
    padding: 0 18px 56px;
    grid-template-columns: 1fr;
    grid-auto-rows: auto;
    gap: 14px;
  }
  .lp-s74, .lp-s54, .lp-s73, .lp-s53,
  .lp-s72, .lp-s52, .lp-s43, .lp-s42 {
    grid-column: 1 / -1;
    grid-row: auto;
    min-height: 180px;
  }

  .lp-cell { padding: 22px; }
  .lp-cell:hover { transform: none; }

  .lp-iata { font-size: 36px; }
  .lp-route-row { flex-wrap: wrap; row-gap: 8px; }
  .lp-rmeta-row { flex-wrap: wrap; gap: 16px; }

  .lp-bp-route { font-size: 22px; }
  .lp-bp-fields { gap: 10px; }

  .lp-trust-score { font-size: 32px; }

  .lp-tagline { font-size: 19px; }

  .lp-net-canvas { height: 100px; }

  .lp-footer {
    padding: 24px 18px;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .lp-modal { padding: 28px 22px; border-radius: 20px; margin: 12px; }
  .lp-mtitle { font-size: 22px; }
}
`

export default function LandingPage() {
  const { token } = useAuthStore()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [modalOpen, setModalOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [successEmail, setSuccessEmail] = useState('')
  const [submitError, setSubmitError] = useState('')
  const nameRef = useRef<HTMLInputElement>(null)
  // T_UX.4 D — landing is the "home" for every visitor now; authed users
  // can still see it via the logo. Nav CTA switches to Dashboard for them.
  const isAuthed = !!token

  const openModal = () => {
    setModalOpen(true)
    setTimeout(() => nameRef.current?.focus(), 220)
  }

  const closeModal = () => {
    setModalOpen(false)
    setSubmitted(false)
    setSubmitError('')
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const email = (form.elements.namedItem('email') as HTMLInputElement).value.trim()
    const name = (form.elements.namedItem('name') as HTMLInputElement).value.trim()
    setSubmitting(true)
    setSubmitError('')
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, source: 'landing' }),
      })
      if (res.ok || res.status === 409) {
        setSuccessEmail(email)
        setSubmitted(true)
      } else {
        const detail = await res.json().catch(() => ({ detail: 'Something went wrong' }))
        setSubmitError(detail?.detail || 'Something went wrong')
      }
    } catch {
      setSubmitError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="lp">
      <style dangerouslySetInnerHTML={{ __html: LP_CSS }} />

      {/* NAV */}
      <nav className="lp-nav">
        <a href="/" className="lp-wordmark">Vimana<span>.</span></a>
        <span className="lp-nav-tag">SACRED LOGISTICS · V0.01.17 · PHASE 1</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <LanguageSwitcher />
          {isAuthed ? (
            <button className="lp-cta" onClick={() => navigate('/dashboard')}>
              {t('landing.ctaDashboard')}
            </button>
          ) : (
            <button className="lp-cta" onClick={openModal}>
              {t('landing.cta')}
            </button>
          )}
        </div>
      </nav>

      {/* HERO */}
      <section className="lp-hero">
        <p className="lp-eyebrow">{t('landing.eyebrow')}</p>
        <h1 className="lp-h1">
          {t('landing.hero1')}<br />
          {t('landing.hero2')} <em>{t('landing.heroEm')}</em><br />
          {t('landing.hero3')}
        </h1>
        <p className="lp-sub">{t('landing.sub')}</p>
      </section>

      {/* BENTO */}
      <div className="lp-bento">

        {/* ROUTE 7×4 */}
        <div className="lp-cell lp-s74 lp-route">
          <div className="lp-clabel">{t('landing.routeLabel')}</div>
          <div className="lp-route-row">
            <div><div className="lp-iata">DXB</div><div className="lp-iata-city">Dubai International</div></div>
            <div className="lp-arrow">✈</div>
            <div><div className="lp-iata">JFK</div><div className="lp-iata-city">New York Kennedy</div></div>
          </div>
          <div className="lp-rmeta-row">
            <div className="lp-rmeta"><label>{t('landing.routeCarrier')}</label><span>Anastasia K.</span></div>
            <div className="lp-rmeta"><label>{t('landing.routeDeparts')}</label><span style={{ color: 'var(--lp-sky)' }}>14 JUL · 02:35</span></div>
            <div className="lp-rmeta"><label>{t('landing.routeCapacity')}</label><span style={{ color: 'var(--lp-amber)' }}>2.5 kg free</span></div>
            <div className="lp-rmeta"><label>{t('landing.routeTrust')}</label><span style={{ color: 'var(--lp-gold)' }}>УБА 731 ✦</span></div>
          </div>
          <div className="lp-tags">
            <span className="lp-tag">document</span>
            <span className="lp-tag">medicine</span>
            <span className="lp-tag">gift</span>
            <span className="lp-tag">electronics</span>
            <span className="lp-tag">animal</span>
          </div>
        </div>

        {/* VAULT 5×4 */}
        <div className="lp-cell lp-s54 lp-vault">
          <div className="lp-clabel">{t('landing.vaultLabel')}</div>
          <div className="lp-ctitle" style={{ marginBottom: '14px' }}>{t('landing.vaultTitle')}</div>
          <div className="lp-vrow"><span>📦</span><span className="lp-vtext">{t('landing.vaultE1')}</span><span className="lp-vtime">14:22 UTC</span></div>
          <div className="lp-vrow"><span>✈️</span><span className="lp-vtext">{t('landing.vaultE2')} · EK201</span><span className="lp-vtime">02:35 UTC</span></div>
          <div className="lp-vrow"><span>📸</span><span className="lp-vtext">{t('landing.vaultE3')}</span><span className="lp-vtime">11:07 UTC</span></div>
          <div className="lp-vrow lp-ok"><span>✅</span><span className="lp-vtext">{t('landing.vaultE4')}</span><span className="lp-vtime">11:09 UTC</span></div>
          <div className="lp-vault-badge">{t('landing.vaultSha')}</div>
        </div>

        {/* BOARDING PASS 7×3 */}
        <div className="lp-cell lp-s73 lp-boarding">
          <div className="lp-bp-inner">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="lp-bp-brand">{t('landing.boardingBrand')}</div>
              <div className="lp-bp-id">VMN-2026-07841</div>
            </div>
            <div className="lp-bp-route">DXB → JFK</div>
            <div className="lp-bp-fields">
              <div className="lp-bpf"><label>{t('landing.boardingSender')}</label><span>Mikhail O.</span></div>
              <div className="lp-bpf"><label>{t('landing.boardingCarrier')}</label><span>Anastasia K.</span></div>
              <div className="lp-bpf"><label>{t('landing.boardingCargo')}</label><span>Document · 0.4 kg</span></div>
              <div className="lp-bpf"><label>{t('landing.boardingStatus')}</label><span><span className="lp-sdot" />{t('landing.boardingConfirmed')}</span></div>
            </div>
          </div>
        </div>

        {/* TRUST 5×3 */}
        <div className="lp-cell lp-s53 lp-trust">
          <div className="lp-clabel">{t('landing.trustLabel')}</div>
          <div className="lp-trust-score">731</div>
          <div style={{ fontSize: '12px', color: 'var(--lp-muted)', marginBottom: '2px' }}>{t('landing.trustRank')}</div>
          <div className="lp-trust-bar"><div className="lp-trust-fill" /></div>
          <div className="lp-tiers">
            <span className="lp-tier">{t('landing.tier1')}</span>
            <span className="lp-tier">{t('landing.tier2')}</span>
            <span className="lp-tier">{t('landing.tier3')}</span>
            <span className="lp-tier lp-on">{t('landing.tier4')}</span>
            <span className="lp-tier">{t('landing.tier5')}</span>
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-muted)', marginTop: '12px' }}>
            F × Q × V × D_factor · rolling 90d
          </div>
        </div>

        {/* TAGLINE 4×3 */}
        <div className="lp-cell lp-s43 lp-tagline-cell">
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '9px', letterSpacing: '0.15em', color: 'rgba(248,247,244,0.28)', textTransform: 'uppercase' }}>Peer-to-Air</div>
          <div className="lp-tagline">
            {t('landing.tagline1')}<br />
            <em>{t('landing.tagline2')}</em><br />
            {t('landing.tagline3')}<br />
            <em>{t('landing.tagline4')}</em>
          </div>
        </div>

        {/* ESCROW 4×3 */}
        <div className="lp-cell lp-s43 lp-escrow">
          <div className="lp-clabel">{t('landing.escrowLabel')}</div>
          <div className="lp-ctitle" style={{ marginBottom: '4px' }}>{t('landing.escrowTitle')}</div>
          <div className="lp-esc-row">
            <div className="lp-epty"><div className="lp-eicon">📤</div><div className="lp-elabel">{t('landing.escrowSender')}</div></div>
            <div style={{ fontSize: '20px', color: 'var(--lp-muted)' }}>🔐</div>
            <div className="lp-epty"><div className="lp-eicon">✈️</div><div className="lp-elabel">{t('landing.escrowCarrier')}</div></div>
            <div style={{ fontSize: '16px', color: 'var(--lp-muted)' }}>⚖️</div>
            <div className="lp-epty"><div className="lp-eicon" style={{ borderColor: 'rgba(168,110,8,0.2)' }}>🏛️</div><div className="lp-elabel">{t('landing.escrowArbiter')}</div></div>
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-success)', marginTop: '6px' }}>{t('landing.escrowNote')}</div>
        </div>

        {/* NETWORK 4×3 */}
        <div className="lp-cell lp-s43">
          <div className="lp-clabel">{t('landing.networkLabel')}</div>
          <div className="lp-ctitle" style={{ marginBottom: '4px' }}>{t('landing.networkTitle')}</div>
          <div className="lp-net-canvas">
            <div className="lp-nline" style={{ left: '54px', top: '20px', width: '68px', transform: 'rotate(18deg)' }} />
            <div className="lp-nline" style={{ left: '122px', top: '14px', width: '66px', transform: 'rotate(32deg)' }} />
            <div className="lp-nline" style={{ left: '54px', top: '20px', width: '88px', transform: 'rotate(58deg)' }} />
            <div className="lp-nline" style={{ left: '122px', top: '48px', width: '62px', transform: 'rotate(-15deg)' }} />
            <div className="lp-nnode" style={{ left: '26px', top: '6px' }}>👤</div>
            <div className="lp-nnode" style={{ left: '94px', top: '0px' }}>👤</div>
            <div className="lp-nnode" style={{ left: '60px', top: '46px' }}>👤</div>
            <div className="lp-nnode" style={{ left: '162px', top: '28px' }}>👤</div>
            <div className="lp-nnode" style={{ left: '180px', top: '60px' }}>👤</div>
          </div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-muted)' }}>{t('landing.networkSub')}</div>
        </div>

        {/* CORRIDOR 4×2 */}
        <div className="lp-cell lp-s42 lp-sky-cell">
          <div className="lp-clabel">{t('landing.corridorLabel')}</div>
          <div style={{ display: 'flex', gap: '20px', marginTop: '10px', alignItems: 'flex-end' }}>
            <div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: '36px', fontWeight: 700, letterSpacing: '-1px', lineHeight: 1, color: 'var(--lp-sky)' }}>UAE</div>
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-muted)', marginTop: '2px' }}>{t('landing.corridorOrigin')}</div>
            </div>
            <div style={{ color: 'var(--lp-amber)', fontSize: '20px', paddingBottom: '4px' }}>↔</div>
            <div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: '36px', fontWeight: 700, letterSpacing: '-1px', lineHeight: 1, color: 'var(--lp-navy)' }}>USA</div>
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-muted)', marginTop: '2px' }}>{t('landing.corridorDest')}</div>
            </div>
          </div>
        </div>

        {/* NOSTR 4×2 */}
        <div className="lp-cell lp-s42 lp-sky-cell">
          <div className="lp-clabel" style={{ color: 'var(--lp-sky)' }}>{t('landing.nostrLabel')}</div>
          <div className="lp-ctitle" style={{ marginBottom: '6px' }}>{t('landing.nostrTitle')}</div>
          <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', color: 'var(--lp-muted)', lineHeight: '1.7' }}>
            secp256k1 keypair per user<br />
            DealVault events signed · verifiable<br />
            <span style={{ color: 'var(--lp-sky)' }}>npub</span> · self-custody path · NIP-07
          </div>
        </div>

        {/* PROGRESS 4×2 */}
        <div className="lp-cell lp-s42">
          <div className="lp-clabel">{t('landing.progressLabel')}</div>
          <div className="lp-prow">
            <div className="lp-pdot" style={{ background: 'var(--lp-success)' }} />
            <div className="lp-pname">{t('landing.phase1')}</div>
            <div className="lp-pver">v0.01.17</div>
          </div>
          <div className="lp-prow">
            <div className="lp-pdot" style={{ background: 'var(--lp-border)' }} />
            <div className="lp-pname lp-dim">{t('landing.phase2')}</div>
            <div className="lp-pver lp-dim">{t('landing.phaseNext')}</div>
          </div>
          <div className="lp-prow">
            <div className="lp-pdot" style={{ background: 'var(--lp-border)' }} />
            <div className="lp-pname lp-dim">{t('landing.phase5')}</div>
            <div className="lp-pver lp-dim">{t('landing.phasePlanned')}</div>
          </div>
        </div>

        {/* MISSIONS 7×2 */}
        <div className="lp-cell lp-s72 lp-gold-cell">
          <div className="lp-clabel" style={{ color: 'var(--lp-gold)' }}>{t('landing.missionsLabel')}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: '22px', fontWeight: 700, color: 'var(--lp-navy)' }}>{t('landing.missionsTitle')}</div>
              <div style={{ fontSize: '12px', color: 'var(--lp-mid)', lineHeight: '1.55', margin: '8px 0 12px', maxWidth: '320px' }}>{t('landing.missionsDesc')}</div>
              <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '11px', color: 'var(--lp-gold)', fontStyle: 'italic' }}>{t('landing.missionsTagline')}</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flexShrink: 0, marginLeft: '24px' }}>
              {['Urgent', 'Premium', 'High Trust'].map(tag => (
                <span key={tag} style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: '10px', padding: '4px 10px', borderRadius: '5px', background: 'rgba(168,110,8,0.08)', border: '1px solid rgba(168,110,8,0.18)', color: 'var(--lp-gold)' }}>{tag}</span>
              ))}
            </div>
          </div>
        </div>

        {/* PLATFORM 5×2 */}
        <div className="lp-cell lp-s52 lp-warm-cell">
          <div className="lp-clabel">{t('landing.platformLabel')}</div>
          <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: '16px', fontWeight: 600, color: 'var(--lp-navy)', margin: '6px 0', lineHeight: '1.3' }}>{t('landing.platformTitle')}</div>
          <div style={{ fontSize: '12px', color: 'var(--lp-mid)', lineHeight: '1.6' }}>
            {t('landing.platformNote1')}{' '}
            <span style={{ color: 'var(--lp-sky)' }}>{t('landing.platformKey')}</span>
            {t('landing.platformNote2')}
          </div>
        </div>

      </div>

      {/* FOOTER */}
      <footer className="lp-footer">
        <span className="lp-fmono">VIMANA · SACRED LOGISTICS · © 2026</span>
        <span className="lp-fmono">{t('landing.footerTagline')}</span>
        <span className="lp-fmono" style={{ color: 'var(--lp-amber)' }}>DXB ↔ JFK · Phase 1</span>
      </footer>

      {/* MODAL */}
      {modalOpen && (
        <div className="lp-overlay" onClick={(e) => { if (e.target === e.currentTarget) closeModal() }}>
          <div className="lp-modal">
            <button className="lp-mclose" onClick={closeModal}>×</button>
            {submitted ? (
              <div className="lp-msuccess">
                <div className="lp-check">✈️</div>
                <h3>{t('landing.modalSuccessTitle')}</h3>
                <p>{t('landing.modalSuccessText', { email: successEmail })}</p>
              </div>
            ) : (
              <>
                <div className="lp-meyebrow">{t('landing.modalEyebrow')}</div>
                <h2 className="lp-mtitle">{t('landing.modalTitle')}</h2>
                <p className="lp-msub">{t('landing.modalSub')}</p>
                <form onSubmit={handleSubmit}>
                  <div className="lp-mfield">
                    <label>{t('landing.modalName')}</label>
                    <input ref={nameRef} name="name" type="text" placeholder={t('landing.modalNamePh')} autoComplete="name" />
                  </div>
                  <div className="lp-mfield">
                    <label>{t('landing.modalEmail')} *</label>
                    <input name="email" type="email" placeholder={t('landing.modalEmailPh')} required autoComplete="email" />
                  </div>
                  {submitError && (
                    <div style={{ color: 'var(--lp-amber)', fontSize: '12px', fontFamily: "'IBM Plex Mono',monospace", marginBottom: '10px' }}>
                      {submitError}
                    </div>
                  )}
                  <button type="submit" className="lp-msubmit" disabled={submitting}>
                    {submitting ? t('landing.modalSending') : t('landing.modalSubmit')}
                  </button>
                </form>
                <div className="lp-mfine">{t('landing.modalFine')}</div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
