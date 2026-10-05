import type { ReactNode } from 'react'

export function PageHeading({ eyebrow, title, lede, action }: { eyebrow: string; title: string; lede: ReactNode; action?: ReactNode }) { return <section className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lede">{lede}</p></div>{action}</section> }

export function Stat({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="card stat-card"><p className="eyebrow">{label}</p><strong>{value}</strong><small>{detail}</small></article> }
