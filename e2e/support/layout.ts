import type { Page } from '@playwright/test'

// Content that extends past the viewport or past the card that contains it (clipped or
// spilling text, images, tables). Visually-hidden text is excluded by its 1px size.
export const outOfBounds = (page: Page) => page.evaluate(() => {
  const problems: string[] = []
  const viewport = document.documentElement.clientWidth
  for (const element of Array.from(document.querySelectorAll<HTMLElement>('#main-content *'))) {
    const rect = element.getBoundingClientRect()
    if (rect.width <= 1 || rect.height <= 1) continue
    const name = `${element.tagName.toLowerCase()}.${String(element.className).split(' ').filter(Boolean).slice(0, 2).join('.')} "${(element.textContent ?? '').trim().slice(0, 30)}"`
    if (rect.right > viewport + 1 || rect.left < -1) { problems.push(`outside viewport: ${name}`); continue }
    const card = element.parentElement?.closest<HTMLElement>('.card')
    if (card) {
      const box = card.getBoundingClientRect()
      if (rect.right > box.right + 1 || rect.left < box.left - 1) problems.push(`outside its card: ${name}`)
    }
  }
  return problems.slice(0, 10)
})
