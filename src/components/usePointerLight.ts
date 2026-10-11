import { useEffect } from 'react'
import type { RefObject } from 'react'
import { cancelTick, publishMagnet, publishPointer, requestTick, subscribeScroll } from './backgroundRuntime'

// Elements that receive a local, pointer-following highlight (the innermost one under the
// pointer). Styles: `.card::before` / `.card::after` in src/theme.css.
export const SPOTLIGHT_SELECTOR = '.card'
// Interactive cards (each opens something) that gently attract nearby skill-graph capsules
// while hovered. Opt-in metadata on the component, not a styling class.
export const MAGNET_SELECTOR = '[data-graph-magnet]'
// The secondary (teal) light trails the primary one for depth; this is the fraction of
// the remaining distance it covers per frame.
const TRAIL_EASING = 0.16

// One pointer listener for the whole app, driving both the global ambient spotlight and the
// card spotlights, and publishing the latest sample and hovered interactive card to the skill
// graph (pointer feed).
// Pointer events only record the latest position; updates run through the shared frame
// scheduler (one requestAnimationFrame per frame for all background subsystems).
// No React state changes: positions are written to `transform` and CSS custom properties.
// Tracking is active only for a fine, hover-capable pointer (mouse/trackpad) and when the
// user has not asked for reduced motion; touch input is ignored, and no event is ever
// prevented, so selection, drag-and-drop, uploads and forms behave exactly as before.
export function usePointerLight(rootRef: RefObject<HTMLDivElement | null>, primaryRef: RefObject<HTMLSpanElement | null>, secondaryRef: RefObject<HTMLSpanElement | null>) {
  useEffect(() => {
    const root = rootRef.current, primary = primaryRef.current, secondary = secondaryRef.current
    if (!root || !primary || !secondary) return
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

    const TICK = 'pointer-light'
    let tracking = false
    let inside = false
    let target = { x: 0, y: 0 }
    let trail = { x: 0, y: 0 }
    let hoverTarget: Element | null = null
    let hitTestPending = false
    let litCard: HTMLElement | null = null
    let unsubscribeScroll: () => void = () => undefined

    // React rewrites a card's whole class attribute when its className prop changes (e.g. the
    // dashboard banner going from loading to "success"), which would drop the imperatively
    // added `is-lit` under a resting pointer. While a card is lit, a MutationObserver on that
    // one element's class attribute puts it back (not polling; disconnected on change).
    const keepLit = typeof MutationObserver === 'function'
      ? new MutationObserver(() => { if (litCard && !litCard.classList.contains('is-lit')) litCard.classList.add('is-lit') })
      : null
    const light = (card: HTMLElement | null) => {
      if (card === litCard) return
      keepLit?.disconnect()
      litCard?.classList.remove('is-lit')
      litCard = card
      card?.classList.add('is-lit')
      if (card) keepLit?.observe(card, { attributes: true, attributeFilter: ['class'] })
    }

    const render = () => {
      if (!tracking) return
      if (inside) {
        // Reads first (hit test, one rect), then writes — no forced reflow loop.
        if (hitTestPending) { hoverTarget = document.elementFromPoint(target.x, target.y); hitTestPending = false }
        const card = hoverTarget?.closest<HTMLElement>(SPOTLIGHT_SELECTOR) ?? null
        const rect = card?.getBoundingClientRect()
        primary.style.transform = `translate3d(${target.x}px, ${target.y}px, 0)`
        trail = { x: trail.x + (target.x - trail.x) * TRAIL_EASING, y: trail.y + (target.y - trail.y) * TRAIL_EASING }
        secondary.style.transform = `translate3d(${trail.x}px, ${trail.y}px, 0)`
        light(card)
        if (card && rect) {
          card.style.setProperty('--sx', `${target.x - rect.left}px`)
          card.style.setProperty('--sy', `${target.y - rect.top}px`)
        }
        const magnet = card?.closest(MAGNET_SELECTOR) ?? null
        const box = magnet === card ? rect : magnet?.getBoundingClientRect()
        publishMagnet(magnet && box ? { x: box.left, y: box.top, w: box.width, h: box.height } : null, magnet)
        // Keep animating only while the trailing light is still catching up.
        if (Math.abs(target.x - trail.x) > 0.5 || Math.abs(target.y - trail.y) > 0.5) schedule()
      } else {
        light(null)
        publishMagnet(null)
      }
    }
    const schedule = () => requestTick(TICK, render)

    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') return
      target = { x: event.clientX, y: event.clientY }
      hoverTarget = event.target instanceof Element ? event.target : null
      if (!inside) { inside = true; trail = { ...target }; root.dataset.pointer = 'in' }
      publishPointer({ x: target.x, y: target.y, time: event.timeStamp, inside: true })
      schedule()
    }
    const onOut = (event: PointerEvent) => {
      if (event.relatedTarget !== null) return   // moving between elements, not leaving the window
      inside = false
      root.dataset.pointer = 'out'
      publishPointer({ x: target.x, y: target.y, time: event.timeStamp, inside: false })
      schedule()
    }
    // Content scrolls under a still pointer: re-check which card is underneath.
    const onScroll = () => { if (inside) { hitTestPending = true; schedule() } }

    const start = () => {
      if (tracking) return
      tracking = true
      root.dataset.tracking = 'on'
      window.addEventListener('pointermove', onMove, { passive: true })
      window.addEventListener('pointerout', onOut, { passive: true })
      unsubscribeScroll = subscribeScroll(onScroll)
    }
    const stop = () => {
      tracking = false
      inside = false
      root.dataset.tracking = 'off'
      root.dataset.pointer = 'out'
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerout', onOut)
      unsubscribeScroll()
      unsubscribeScroll = () => undefined
      cancelTick(TICK)
      publishPointer({ x: target.x, y: target.y, time: performance.now(), inside: false })
      publishMagnet(null)
      light(null)
    }
    const update = () => { if (finePointer.matches && !reducedMotion.matches) start(); else stop() }

    update()
    finePointer.addEventListener('change', update)
    reducedMotion.addEventListener('change', update)
    return () => {
      finePointer.removeEventListener('change', update)
      reducedMotion.removeEventListener('change', update)
      stop()
    }
  }, [rootRef, primaryRef, secondaryRef])
}
