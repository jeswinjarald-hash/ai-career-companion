import { useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'

// Circular meter for a single real percentage (0–100). The arc length is exactly `value`
// percent of the circle; `null` means the value is not available and draws no arc and no
// number (never a 0). The accessible name carries the value; the drawing is decorative.
export function ScoreRing({ value, label, size = 112, caption }: { value: number | null; label: string; size?: number; caption?: string }) {
  const gradientId = useId()
  const stroke = Math.max(6, Math.round(size / 11))
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = value === null ? null : Math.min(100, Math.max(0, value))
  const offset = clamped === null ? circumference : circumference * (1 - clamped / 100)
  const style = { '--ring-circumference': `${circumference}`, '--ring-font': `${Math.round(size / 4.4)}px` } as CSSProperties
  return <div className={`score-ring ${clamped === null ? 'unavailable' : ''}`} role="img" aria-label={clamped === null ? `${label}: not available` : `${label}: ${Math.round(clamped)}%`} style={style}>
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" focusable="false">
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#4f8cff" /><stop offset="55%" stopColor="#b16cff" /><stop offset="100%" stopColor="#43e6d0" /></linearGradient></defs>
      <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
      {clamped !== null && clamped > 0 && <circle className="ring-value" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} stroke={`url(#${gradientId})`} strokeDasharray={circumference} strokeDashoffset={offset} />}
    </svg>
    <div className="score-ring-label" aria-hidden="true"><strong>{clamped === null ? '—' : `${Math.round(clamped)}%`}</strong>{caption && <span>{clamped === null ? 'Not available' : caption}</span>}</div>
  </div>
}

// Accessible horizontal bar chart. The data is a real <table> (row header, value and
// optional detail column), so screen readers and keyboard users get the exact figures;
// the bars are decorative (aria-hidden) and scaled linearly from 0 to `max`.
// A row with value === null is "not available" and is drawn without a bar — never as 0.
export type MeterRow = { key: string; label: ReactNode; value: number | null; display: string; detail?: string; muted?: boolean }

export function MeterChart({ title, description, rows, max, labelHeader, valueHeader, detailHeader, emptyText }: {
  title: string
  description?: ReactNode
  rows: MeterRow[]
  max: number
  labelHeader: string
  valueHeader: string
  detailHeader?: string
  emptyText: string
}) {
  const hasDetail = detailHeader !== undefined && rows.some((row) => row.detail)
  return <figure className="chart">
    <figcaption><strong>{title}</strong>{description && <span>{description}</span>}</figcaption>
    {rows.length === 0 ? <p className="muted">{emptyText}</p> : <table className="meter-table">
      <thead><tr><th scope="col">{labelHeader}</th><th scope="col"><span className="visually-hidden">Bar</span></th><th scope="col" className="meter-value-head">{valueHeader}</th>{hasDetail && <th scope="col">{detailHeader}</th>}</tr></thead>
      <tbody>{rows.map((row) => {
        const width = row.value === null || max <= 0 ? 0 : Math.min(100, Math.max(0, (row.value / max) * 100))
        return <tr key={row.key}>
          <th scope="row">{row.label}</th>
          <td>{row.value === null ? <span className="meter-na">Not available</span> : <div className={`meter-bar ${row.muted ? 'muted-bar' : ''}`} aria-hidden="true"><span style={{ width: `${width}%` }} /></div>}</td>
          <td className="meter-value">{row.display}</td>
          {hasDetail && <td className="meter-detail">{row.detail}</td>}
        </tr>
      })}</tbody>
    </table>}
  </figure>
}
