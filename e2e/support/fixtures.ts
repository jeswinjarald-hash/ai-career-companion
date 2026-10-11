import { randomBytes } from 'node:crypto'
import { test as base, expect, type Locator, type Page, type Request } from '@playwright/test'

export const API_URL = 'http://localhost:8100'
export const WEB_URL = 'http://localhost:5174'

export type TestAccount = { fullName: string; email: string; password: string }

// A fresh account per test on the isolated e2e database: tests never share or depend
// on each other's state. The password is random per run and never printed or stored
// (tracing is off by default — see playwright.config.ts).
export const newAccount = (label: string): TestAccount => ({
  fullName: `E2E ${label}`,
  email: `e2e.${label}.${Date.now()}.${randomBytes(3).toString('hex')}@example.com`,
  password: `pw-${randomBytes(12).toString('hex')}`,
})

// Registers through the real API using the page's own request context, so the session
// cookie is shared with the browser exactly as a UI sign-up would leave it. Fails the
// test immediately if registration does not succeed. Returns the created profile id.
export async function registerViaApi(page: Page, account: TestAccount): Promise<number> {
  const response = await page.request.post(`${API_URL}/api/auth/register`, {
    data: { full_name: account.fullName, email: account.email, password: account.password, confirm_password: account.password },
  })
  expect(response.status(), 'test account registration').toBe(201)
  return (await response.json() as { profile: { id: number } }).profile.id
}

// Types a secret into an input without the value appearing anywhere Playwright records
// steps: locator.fill() titles its step 'Fill "<text>"', which the HTML report, traces
// and error logs keep. The value is set through the native setter and announced with an
// input event, exactly as typing does, so React's controlled inputs update normally.
export async function fillSecret(locator: Locator, secret: string): Promise<void> {
  await locator.evaluate((element, value) => {
    const input = element as HTMLInputElement
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }, secret)
  await expect(locator).not.toHaveValue('')
}

// Waits for finite animations (page/drawer entry transitions) to finish, so scans and
// screenshots see the settled page. Infinite ones (loading spinners) are ignored.
export async function settleAnimations(page: Page): Promise<void> {
  await page.evaluate(() => Promise.all(document.getAnimations()
    .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
    .map((animation) => animation.finished.catch(() => undefined))))
}

type StatusPredicate = (url: string, status: number) => boolean
export type NetworkGuard = { problems: string[]; allowStatus: (predicate: StatusPredicate) => void }

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])
const hostOf = (url: string) => { try { return new URL(url).hostname } catch { return '' } }
const isLocal = (url: string) => { try { const { protocol, hostname } = new URL(url); return !protocol.startsWith('http') || LOCAL_HOSTS.has(hostname) } catch { return true } }
// Security software on the development machine (Kaspersky's web protection) injects a
// script from its own domain into every page the browser loads, including localhost.
// Requests to it are still blocked like any other external request; they are just not
// counted as an application failure. Nothing else is exempt.
const INJECTED_BY_LOCAL_SECURITY_SOFTWARE = [/(^|.)kaspersky-labs.com$/]
const isInjectedBySecuritySoftware = (url: string) => INJECTED_BY_LOCAL_SECURITY_SOFTWARE.some((pattern) => pattern.test(hostOf(url)))

// Records browser-side problems for one page: uncaught errors, console errors, failed
// requests and HTTP errors from the app (Vite on WEB_URL) or the API. A 4xx is accepted
// only when the test explicitly expects it; a 5xx never is. Requests to any non-local
// host are blocked and reported, so the suite cannot reach the network.
export async function createNetworkGuard(page: Page): Promise<NetworkGuard> {
  const problems: string[] = []
  const allowed: StatusPredicate[] = []
  const isAllowed = (url: string, status: number) => status < 500 && allowed.some((predicate) => predicate(url, status))
  const statusByRequest = new WeakMap<Request, number>()

  await page.context().route((url) => !isLocal(url.toString()), (route) => {
    if (!isInjectedBySecuritySoftware(route.request().url())) problems.push(`external request blocked: ${route.request().method()} ${route.request().url()}`)
    return route.abort('blockedbyclient')
  })

  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    if (message.text().includes('net::ERR_BLOCKED_BY_CLIENT') && isInjectedBySecuritySoftware(message.location().url)) return
    // The browser logs every HTTP error as "Failed to load resource: … status of N";
    // those are judged by their URL and status (the same rule as responses below).
    const failed = /^Failed to load resource: the server responded with a status of (\d+)/.exec(message.text())
    if (failed && isAllowed(message.location().url, Number(failed[1]))) return
    problems.push(`console: ${message.text()} ${message.location().url}`)
  })
  page.on('response', (response) => {
    statusByRequest.set(response.request(), response.status())
    const status = response.status()
    // The Vite dev server answers a missing stylesheet/script with its SPA fallback
    // (200 text/html) rather than a 404, so a missing asset is recognised by its type.
    const kind = response.request().resourceType()
    if ((kind === 'stylesheet' || kind === 'script') && status < 400 && (response.headers()['content-type'] ?? '').startsWith('text/html')) {
      problems.push(`missing ${kind} (served as HTML fallback): ${response.url()}`)
      return
    }
    if (status < 400 || isAllowed(response.url(), status)) return
    problems.push(`http ${status}: ${response.request().method()} ${response.url()}`)
  })
  page.on('requestfailed', (request) => {
    // Known Chrome quirk: the bodiless 204 from POST /api/auth/logout reaches fetch()
    // but is also reported as net::ERR_ABORTED. Accepted only in exactly that case.
    const knownLogoutQuirk = request.method() === 'POST' && request.url() === `${API_URL}/api/auth/logout`
      && request.failure()?.errorText === 'net::ERR_ABORTED' && statusByRequest.get(request) === 204
    if (knownLogoutQuirk || !isLocal(request.url())) return // external requests are already reported when blocked
    problems.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`)
  })
  return { problems, allowStatus: (predicate) => allowed.push(predicate) }
}

type Guard = Pick<NetworkGuard, 'allowStatus'>

export const test = base.extend<{ guard: Guard }>({
  guard: [async ({ page }, use) => {
    const guard = await createNetworkGuard(page)
    await use(guard)
    expect(guard.problems, 'browser console / network problems').toEqual([])
  }, { auto: true }],
})

export const allowSignedOutCheck = (guard: Guard) => guard.allowStatus((url, status) => status === 401 && url === `${API_URL}/api/auth/me`)

export { expect }
