import type { Page } from '@playwright/test'
import { settleAnimations } from './fixtures'

// Measured text contrast on the rendered page. axe cannot compute contrast over gradient
// or translucent backgrounds (it reports those as "incomplete"), so this measures pixels:
// 1. record each visible text element's colour, size and box;
// 2. make all text transparent and capture the page — leaving only what is behind the text;
// 3. take the LIGHTEST and DARKEST background pixel inside each box (worst cases for light
//    and dark text respectively) and compute the WCAG contrast ratio against the text colour.
// Thresholds: 4.5:1, or 3:1 for large text (≥ 24px, or ≥ 18.66px at weight ≥ 700).
// Disabled controls are exempt (WCAG 1.4.3). With a modal open, only the modal is measured.
// Screen-reader-only text and placeholder text are not measured.
type Sample = { text: string; selector: string; color: [number, number, number, number]; required: number; box: { x: number; y: number; w: number; h: number } }

async function collectText(page: Page): Promise<Sample[]> {
  return page.evaluate(() => {
    const parse = (value: string): [number, number, number, number] => {
      const parts = value.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0, 1]
      return [parts[0], parts[1], parts[2], parts[3] ?? 1]
    }
    const samples: Sample[] = []
    // With a modal dialog open, only the dialog is presented; the page behind it is dimmed and inert.
    const root = document.querySelector('[aria-modal="true"]') ?? document.body
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const seen = new Set<Element>()
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const element = node.parentElement
      if (!element || seen.has(element) || !node.textContent?.trim()) continue
      seen.add(element)
      if (element.closest('[aria-hidden="true"]') && !element.closest('.score-ring-label')) continue
      if (element.closest('.visually-hidden')) continue   // screen-reader-only text is never drawn
      if (element.closest('button:disabled, [aria-disabled="true"], input:disabled, textarea:disabled, select, option')) continue
      const style = getComputedStyle(element)
      if (style.visibility === 'hidden' || Number(style.opacity) === 0) continue
      const range = document.createRange(); range.selectNodeContents(node)
      const rect = range.getBoundingClientRect()
      if (rect.width < 2 || rect.height < 2) continue   // visually-hidden helpers
      const size = parseFloat(style.fontSize); const weight = Number(style.fontWeight)
      const large = size >= 24 || (size >= 18.66 && weight >= 700)
      samples.push({
        text: node.textContent.trim().slice(0, 40),
        selector: `${element.tagName.toLowerCase()}${element.className ? '.' + String(element.className).trim().split(/\s+/).slice(0, 2).join('.') : ''}`,
        color: parse(style.color), required: large ? 3 : 4.5,
        box: { x: Math.round(rect.left + window.scrollX), y: Math.round(rect.top + window.scrollY), w: Math.round(rect.width), h: Math.round(rect.height) },
      })
    }
    return samples
  }) as Promise<Sample[]>
}

export async function measure(page: Page, label: string): Promise<string[]> {
  // Freeze the ambient light so the capture is deterministic.
  await page.addStyleTag({ content: '.ambient-orb { animation-play-state: paused !important; }' })
  await settleAnimations(page)
  const samples = await collectText(page)
  const hideText = await page.addStyleTag({ content: '* { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; }' })
  const png = (await page.screenshot({ fullPage: true })).toString('base64')
  await hideText.evaluate((node) => (node as Element).remove())
  const analysis = await page.context().newPage()
  try {
    return await analysis.evaluate(async ({ data, samples: items, label: pageLabel }) => {
      const image = new Image(); image.src = `data:image/png;base64,${data}`; await image.decode()
      const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height
      const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0)
      const channel = (value: number) => { const c = value / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
      const luminance = (r: number, g: number, b: number) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
      const ratio = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
      const failures: string[] = []
      for (const sample of items) {
        const { x, y, w, h } = sample.box
        if (x < 0 || y < 0 || x + w > canvas.width || y + h > canvas.height) continue
        const pixels = context.getImageData(x, y, w, h).data
        let lightest = -1, darkest = 2, light: number[] = [0, 0, 0], dark: number[] = [0, 0, 0]
        for (let i = 0; i < pixels.length; i += 4) {
          const value = luminance(pixels[i], pixels[i + 1], pixels[i + 2])
          if (value > lightest) { lightest = value; light = [pixels[i], pixels[i + 1], pixels[i + 2]] }
          if (value < darkest) { darkest = value; dark = [pixels[i], pixels[i + 1], pixels[i + 2]] }
        }
        // Semi-transparent text is composited over each background candidate first.
        const [r, g, b, a] = sample.color
        const over = (bg: number[]) => luminance(r * a + bg[0] * (1 - a), g * a + bg[1] * (1 - a), b * a + bg[2] * (1 - a))
        const worst = Math.min(ratio(over(light), lightest), ratio(over(dark), darkest))
        if (worst < sample.required) failures.push(`${pageLabel}: ${worst.toFixed(2)}:1 < ${sample.required}:1 — ${sample.selector} "${sample.text}"`)
      }
      return failures
    }, { data: png, samples, label })
  } finally { await analysis.close() }
}

