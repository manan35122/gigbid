import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'

const PERSONAS: Record<string, { name: string; title: string }> = {
  ai_engineer: { name: 'Ayesha Khan', title: 'AI/ML engineer' },
  fullstack_dev: { name: 'Bilal Ahmed', title: 'Full-stack developer' },
  data_analyst: { name: 'Sana Raza', title: 'Data analyst' },
}

const STEP: Record<string, string> = {
  load_job: 'Loading the job and client',
  analyst: 'Extracting requirements',
  risk_assessor: 'Checking for scams and client risk',
  fit_matcher: 'Matching requirements to your portfolio',
  decide: 'Deciding: bid, watch or skip',
  pricing: 'Pricing the bid',
  writer: 'Drafting the proposal',
  verifier: 'Verifying every claim against evidence',
  critic: 'Critic reviewing the draft',
  compliance: 'Checking marketplace rules',
  preview: 'Preparing the dry-run preview',
}

const STATUS: Record<string, string> = {
  new: 'New', running: 'Running', needs_approval: 'Needs your approval', ready_for_approval: 'Ready',
  skipped: 'Skipped', watching: 'Watching', submitted: 'Submitted', rejected: 'Rejected',
  needs_attention: 'Needs attention', blocked: 'Blocked by compliance', approved: 'Approved', edited: 'Edited',
}
const label = (s?: string | null) => (s ? STATUS[s] ?? s : '')

async function api(path: string, init?: RequestInit) {
  const r = await fetch('/api' + path, init)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

const FILTERS: [string, string][] = [
  ['all', 'All'], ['new', 'New'], ['needs_approval', 'Needs approval'], ['submitted', 'Submitted'], ['skipped', 'Skipped'],
]

function Inbox({ persona, open }: { persona: string; open: (id: string) => void }) {
  const [jobs, setJobs] = useState<any[] | null>(null)
  const [err, setErr] = useState('')
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  useEffect(() => {
    setJobs(null); setErr('')
    api(`/jobs?persona=${persona}&limit=50`).then(setJobs).catch((e) => setErr(String(e.message)))
  }, [persona])
  const shown = useMemo(() => (jobs ?? []).filter((j) =>
    (filter === 'all' || j.status === filter) &&
    (!q || (j.title + ' ' + j.skills.join(' ')).toLowerCase().includes(q.toLowerCase()))), [jobs, filter, q])
  if (err) return <div className="banner" role="alert">Marketplace unavailable. Work is paused and will resume when it is back. <br /><small>{err}</small></div>
  if (!jobs) return <>{[1, 2, 3, 4].map((i) => <div key={i} className="skeleton" />)}</>
  const count = (k: string) => k === 'all' ? jobs.length : jobs.filter((j) => j.status === k).length
  return <>
    <div className="chips">
      {FILTERS.map(([k, l]) => (
        <button key={k} className={`chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{l} ({count(k)})</button>))}
      <span className="spacer" />
      <input aria-label="Search jobs" placeholder="Search title or skill" value={q} onChange={(e) => setQ(e.target.value)} />
    </div>
    {!shown.length && <p className="muted">No jobs match this filter.</p>}
    {shown.map((j) => (
      <div key={j.job_id} className="card job" role="button" tabIndex={0}
        onClick={() => open(j.job_id)} onKeyDown={(e) => e.key === 'Enter' && open(j.job_id)}>
        <div><strong>{j.title}</strong><div className="muted">{j.skills.join(' · ')}</div></div>
        <div className="row">
          <span>${j.budget.min}–{j.budget.max}</span><span className="muted">{j.connects_cost} connects</span>
          {j.action && <span className={`badge ${j.action}`}>{j.action}</span>}
          <span className={`badge ${j.status}`}>{label(j.status)}</span>
        </div>
      </div>))}
  </>
}

function Approval({ p, persona, onResult }: { p: any; persona: string; onResult: (s: any, msg: string) => void }) {
  const [text, setText] = useState<string>(p.draft.cover_letter)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => setText(p.draft.cover_letter), [p.draft.cover_letter])
  const send = async (body: any, msg: string) => {
    setBusy(true); setErr('')
    try {
      onResult(await api(`/runs/${persona}/${p.job_id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      }), msg)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const changed = text.trim() !== p.draft.cover_letter.trim()
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Review and approve</h2>
      {p.warnings.map((w: string, i: number) => <div key={i} className="warn">⚠ {w}</div>)}
      <h3>Claims and their evidence</h3>
      <p className="muted">Hover or focus a highlighted sentence to see the portfolio evidence behind it.</p>
      <p>{p.claims.map((c: any, i: number) => (
        <span key={i}><span className={`claim ${c.verdict}`} tabIndex={c.verdict === 'no_claim' ? -1 : 0}>{c.sentence}
          {Object.keys(c.evidence).length > 0 && <span className="tip">
            {Object.entries(c.evidence).map(([id, e]: any) => <div key={id}><b>{id}</b>: {e.title}<br />{e.text}</div>)}
          </span>}</span>{' '}</span>))}</p>
      <div className="row">
        <span className="badge supported">supported</span><span className="badge partial">partial</span>
        <span className="muted">no colour = no claim about past work</span>
      </div>
      <h3>Edit the cover letter <span className="muted">({words} words)</span></h3>
      <label htmlFor="cl" style={{ display: 'none' }}>Cover letter</label>
      <textarea id="cl" value={text} onChange={(e) => setText(e.target.value)} />
      {p.draft.screening_answers.length > 0 && <><h3>Screening answers</h3>
        <ol>{p.draft.screening_answers.map((a: string, i: number) => <li key={i}>{a}</li>)}</ol></>}
      <h3>What will be sent</h3>
      <p>Bid <b>${p.price.bid_amount}</b> · costs <b>{p.preview.connects_cost ?? '?'}</b> Connects
        {p.preview.balance_after !== undefined && <> (balance after: {p.preview.balance_after})</>}<br />
        <span className="muted">{p.price.rationale}</span></p>
      <p className="muted">Risk {p.risk_report.score.toFixed(2)}: {p.risk_report.explanation}</p>
      {err && <div className="banner" role="alert">{err}</div>}
      <div className="actions">
        {changed && <p className="muted" style={{ margin: '0 0 8px' }}>You changed the text. Save the edit first so it is re-checked before approval.</p>}
        <div className="row">
          <button className="primary" disabled={busy || changed} onClick={() => send({ action: 'approve' }, 'Approved and submitted.')}>
            Approve and submit</button>
          <button disabled={busy || !changed} onClick={() => send({ action: 'edit', edited_text: text }, 'Edit saved and re-checked. Review it again.')}>
            Save edit</button>
          <input aria-label="Rejection reason" placeholder="Reason for rejecting" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button className="danger" disabled={busy} onClick={() => send({ action: 'reject', reason: reason || 'rejected' }, 'Rejected. Nothing was sent.')}>
            Reject</button>
        </div>
      </div>
    </div>)
}

function JobDetail({ snap }: { snap: any }) {
  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>Job detail</h2>
      {snap.spec && <>
        <p><b>{snap.spec.title}</b></p>
        <p className="muted">
          Budget ${snap.spec.budget_min}–{snap.spec.budget_max}
          {snap.spec.timeline_days ? ` · ${snap.spec.timeline_days} days` : ''}
        </p>
        {snap.spec.deliverables?.length > 0 && <><h3>Deliverables</h3>
          <ul>{snap.spec.deliverables.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></>}
        {snap.spec.hidden_needs?.length > 0 && <><h3>Hidden needs</h3>
          <ul>{snap.spec.hidden_needs.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></>}
      </>}
      {snap.fit && <>
        <h3>Requirement to evidence</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead><tr><th align="left">Requirement</th><th align="left">Strength</th><th align="left">Evidence</th></tr></thead>
            <tbody>{snap.fit.matrix.map((m: any, i: number) => (
              <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px 6px 0' }}>{m.requirement}</td>
                <td><span className={`badge ${m.strength === 'strong' ? 'supported' : m.strength === 'partial' ? 'partial' : 'skip'}`}>{m.strength}</span></td>
                <td className="muted">{m.evidence_ids.join(', ')}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <p className="muted">Fit {snap.fit.score} · {snap.fit.reasons.join('; ')}</p>
      </>}
      {snap.risk && <><h3>Risk</h3>
        <p><span className={`badge ${snap.risk.score >= 0.7 ? 'skip' : snap.risk.score >= 0.3 ? 'watch' : 'bid'}`}>
          {snap.risk.score.toFixed(2)}</span> {snap.risk.explanation}</p></>}
      {snap.price && <><h3>Price rationale</h3>
        <p>Bid <b>${snap.price.bid_amount}</b> · {snap.price.connects_cost} Connects<br />
          <span className="muted">{snap.price.rationale}</span></p></>}
      {snap.decision && <><h3>Decision</h3>
        <p><span className={`badge ${snap.decision.action}`}>{snap.decision.action}</span> {snap.decision.reasons.join('; ')}</p></>}
    </div>)
}

function RunView({ persona, jobId, back }: { persona: string; jobId: string; back: () => void }) {
  const [nodes, setNodes] = useState<string[]>([])
  const [snap, setSnap] = useState<any>(null)
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    setNodes([]); setSnap(null); setErr(''); setNotice('')
    const es = new EventSource(`/api/runs/${persona}/${jobId}/stream`)
    es.addEventListener('node', (e) => setNodes((n) => [...n, JSON.parse((e as MessageEvent).data).node]))
    es.addEventListener('done', (e) => { setSnap(JSON.parse((e as MessageEvent).data)); es.close() })
    es.addEventListener('error', (e) => {
      const d = (e as MessageEvent).data
      setErr(d ? JSON.parse(d).error : 'Stream connection lost. Reload to continue.'); es.close()
    })
    return () => es.close()
  }, [persona, jobId])
  const seen: Record<string, number> = {}
  const steps = nodes.map((n) => { seen[n] = (seen[n] ?? 0) + 1; return (STEP[n] ?? n) + (seen[n] > 1 ? ` (pass ${seen[n]})` : '') })
  return (
    <>
      <button onClick={back}>← Back to inbox</button>
      <h2>{jobId} <span className="muted">· {PERSONAS[persona]?.name}</span></h2>
      {notice && <div className="notice" role="status">{notice}</div>}
      {err && <div className="banner" role="alert">{err}</div>}
      {!snap && !err && <div className="card"><b>Agents are working…</b>
        <ul className="steps">
          {steps.map((s, i) => <li key={i}><span className="done">✓</span>{s}</li>)}
          <li><span className="spin" />working</li>
        </ul></div>}
      {snap && <>
        <div className="card">
          <div className="row"><span className={`badge ${snap.status}`}>{label(snap.status)}</span>
            {snap.submission && <span>Submitted as <b>{snap.submission.id}</b>, {snap.submission.connects_spent} Connects spent.</span>}</div>
          {snap.errors.length > 0 && <div className="banner">{snap.errors.join('; ')}</div>}
          <details><summary>Run trace ({snap.trace.length} steps)</summary>
            <ul className="steps">{snap.trace.map((t: any, i: number) => <li key={i}><span className="done">✓</span>{STEP[t.node] ?? t.node}</li>)}</ul></details>
        </div>
        <JobDetail snap={snap} />
      </>}
      {snap?.pending_approval && <Approval p={snap.pending_approval} persona={persona}
        onResult={(s, msg) => { setSnap(s); setNotice(msg); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />}
    </>)
}

function RunRoute({ persona }: { persona: string }) {
  const { id } = useParams()
  const nav = useNavigate()
  return <RunView persona={persona} jobId={id!} back={() => nav('/')} />
}

export default function App() {
  const [persona, setPersona] = useState(Object.keys(PERSONAS)[0])
  const nav = useNavigate()
  const p = PERSONAS[persona]
  return (
    <div className="wrap">
      <header>
        <h1>GigBid</h1>
        <nav className="row"><NavLink to="/">Inbox</NavLink></nav>
        <span className="spacer" />
        <label className="persona">Freelancer profile
          <select value={persona} onChange={(e) => { setPersona(e.target.value); nav('/') }}>
            {Object.entries(PERSONAS).map(([id, v]) => <option key={id} value={id}>{v.name}, {v.title}</option>)}
          </select>
        </label>
      </header>
      <p className="muted" style={{ marginTop: -8 }}>Working for <b>{p.name}</b> ({p.title}). Proposals are written only from this person's portfolio.</p>
      <Routes>
        <Route path="/" element={<Inbox persona={persona} open={(id) => nav(`/jobs/${id}`)} />} />
        <Route path="/jobs/:id" element={<RunRoute persona={persona} />} />
      </Routes>
    </div>)
}