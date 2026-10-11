import { useEffect, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode, RefObject } from 'react'
import { Icon } from './icons'
import { NAV_GROUPS, SETTINGS_ITEM, nav, navSection, type NavItem, type View } from '../routing'

// Grouped primary navigation, shared by the desktop sidebar and the mobile drawer.
export function NavList({ view, onNavigate, label }: { view: View; onNavigate: (view: View) => void; label: string }) {
  const current = navSection(view)
  const item = (entry: NavItem) => <button key={entry.id} className={`nav-item ${current === entry.id ? 'active' : ''}`} aria-current={current === entry.id ? 'page' : undefined} onClick={() => onNavigate(entry.id)}>
    <Icon name={entry.icon} className="nav-icon" /><strong>{entry.label}</strong>
  </button>
  return <>
    <nav aria-label={label}>
      {NAV_GROUPS.map((group) => <div className="nav-group" key={group}>
        <p className="nav-group-label" aria-hidden="true">{group}</p>
        {nav.filter((entry) => entry.group === group).map(item)}
      </div>)}
    </nav>
    <div className="sidebar-divider" />
    <nav aria-label={`${label} — settings`}>{item(SETTINGS_ITEM)}</nav>
  </>
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Small-screen navigation: a modal drawer. Focus moves into it on open, Tab cycles within
// it, Escape or the backdrop closes it, and focus returns to the menu button afterwards.
export function NavDrawer({ open, onClose, children, returnFocusTo }: { open: boolean; onClose: () => void; children: ReactNode; returnFocusTo: RefObject<HTMLButtonElement | null> }) {
  const panelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const returnTarget = returnFocusTo.current
    panelRef.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow; returnTarget?.focus() }
  }, [open, returnFocusTo])
  if (!open) return null

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
    if (event.key !== 'Tab' || !panelRef.current) return
    const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (focusable.length === 0) return
    const first = focusable[0], last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <>
    <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
    <div className="drawer" role="dialog" aria-modal="true" aria-label="Navigation menu" ref={panelRef} onKeyDown={onKeyDown}>
      <div className="drawer-head">
        <div className="brand-mark"><span aria-hidden="true">AC</span><div><strong>AI Career</strong><small>Companion</small></div></div>
        <button className="drawer-close" onClick={onClose} data-autofocus aria-label="Close navigation menu"><Icon name="close" /></button>
      </div>
      {children}
    </div>
  </>
}
