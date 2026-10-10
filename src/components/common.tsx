import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

export function PageHeading({ eyebrow, title, lede, action }: { eyebrow: string; title: string; lede: ReactNode; action?: ReactNode }) { return <section className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{lede && <p className="lede">{lede}</p>}</div>{action && <div className="page-heading-action">{action}</div>}</section> }

export function Stat({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="card stat-card"><p className="eyebrow">{label}</p><strong>{value}</strong><small>{detail}</small></article> }

// A genuine "nothing here yet" state with an optional next step — never a placeholder
// dressed up as data.
export function EmptyState({ title, message, action }: { title?: string; message: ReactNode; action?: ReactNode }) { return <div className="architecture-note empty-state" role="status"><div>{title && <strong>{title}</strong>}<p>{message}</p></div>{action && <div className="empty-state-action">{action}</div>}</div> }

// Feedback for a genuinely long server operation: a real elapsed-time counter and an
// honest description of what is happening — never a simulated percentage, because the
// backend reports no intermediate progress. Nothing is shown as done until the request
// itself returns.
export function LongTaskStatus({ label, detail }: { label: string; detail: string }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return <div className="long-task" role="status" aria-live="polite">
    <span className="spinner" aria-hidden="true" />
    <div><strong>{label}</strong><p>{detail}</p></div>
    <span className="long-task-elapsed" aria-label={`${elapsed} seconds elapsed`}>{elapsed}s</span>
  </div>
}
