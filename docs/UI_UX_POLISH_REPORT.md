# UI/UX Polish and Application Readiness Report

Scope: refinement of the existing, milestone-complete application (React 19 + Vite + TypeScript frontend, FastAPI + SQLAlchemy/SQLite backend, Sentence Transformers + FAISS retrieval, optional OpenAI-compatible LLM layer). No architecture, scoring, retrieval, ranking or generation logic was changed. Date: 2026-10-10, branch `develop`.

## 1. Baseline audit (before any edit)

| Check | Result |
|---|---|
| `pytest -q` (backend) | 464 passed, 1 xfailed |
| `npx tsc -b` | pass |
| `npm run lint` | 0 errors, 1 warning (`react-hooks/exhaustive-deps` in `ProfileView`) |

Confirmed defects, by priority:

- **P1 – mobile navigation:** at ≤ 620 px only 5 of 10 destinations were reachable (Skill Gap, Roadmap, Assistant, Progress and Settings had no entry point), and the top bar overflowed a 375 px viewport (scroll width 384 px, "Sign out" clipped).
- **P1 – stale or mismatched data:** selecting a new file, *before uploading it*, cleared the active processed resume across the app (the dashboard said "No resume analyzed yet" while the backend still had one). After a failed re-upload, the results page could still show the previous resume's structured data.
- **P1 – silent failure:** in Customize Application, a failed "Save edits" stored the error but never rendered it.
- **P1 – unhandled errors:** Assistant conversation select/new/delete and Customize/Interview version switching had no error handling (unhandled promise rejections, no feedback).
- **P1 – session expiry:** a 401 mid-session left each page showing "Authentication required." with no route back to sign-in. If the backend was unreachable at startup, the user saw the login form with no explanation.
- **P1 – misleading figure:** search similarity (`best + 0.05 × Σ others`, unbounded above 1.0) was displayed as "N% relevance".
- **P2 – error text:** 422 responses in six services were rendered with `String(detail)`, which gives "[object Object]" for FastAPI validation lists. The raw Pydantic e-mail validator text reached the signup form.
- **P2 – accessibility:** the resume file input was `display: none` (not keyboard reachable). There were no focus styles for select/textarea/summary, no skip link, no `aria-current`, and no focus management on route change. Validation messages were not associated with inputs, and many 9–11 px text sizes and greys fell below 4.5:1 contrast. Processing icons used the literal text "OK"/"00".
- **P2 – resume processing view:** step progress was not tied to the real requests (only the last step was ever "active").
- **P3 – copy:** "Milestone 2" jargon in the UI, `->` text arrows, `+` text bullets.
- **Security (production):** the session cookie was hard-coded `secure=False`.

What was already sound and was preserved: backend ownership checks (verified below), an honest empty dashboard, application tracker states, grounding and validation badges on generated content, and the deterministic and LLM provenance labels.

## 2. Changes

**Shared request layer (`src/config/api.ts`):** `apiFetch` (credentialed fetch that emits a session-expired event on 401) and `apiDetailMessage` (readable FastAPI errors, generic text for 5xx). All feature services now use it. `authService` keeps raw fetch because a 401 there means "wrong credentials".

**App shell (`src/App.tsx`):**
- New `unreachable` state with a retry button.
- Session expiry clears all in-memory account data and returns to sign-in with an explanation.
- Login and signup switch without full-page reloads, and deep links survive sign-in.
- Logout resets the selected job and application.
- Per-route `document.title`, focus moves to the page `<h1>` on navigation, and the page scrolls to top.
- Skip link, `<main>` landmark, `aria-current` on navigation.
- Mobile nav includes every destination (including Settings) and keeps the active item in view.

**Resume upload and analysis:**
- Client checks mirror the backend (PDF/DOCX, non-empty, ≤ 10 MiB) without clearing the active resume.
- The current resume card shows file name, size and upload time.
- "Choose a different file" and "Remove" actions; drag-over state.
- Duplicate-submit guard: a double click sends one request (verified in the server log).
- Processing steps follow the real sequence of backend calls (upload → extract → sections → structure → context), and a step is only marked done after its request returns. A failed step is shown as failed. A rejected upload leaves the previous resume active. After an accepted upload, the old structured data is never shown as belonging to the new file.

**Results and other screens:**
- Resume Results now has a page heading, provenance line ("From <file>…"), list markup and next-step actions.
- Career Recommendations: matches reset when the resume changes, a request is cancelled when superseded, retry on error, empty states with a next step. Search shows `Relevance 0.75` (raw score with tooltip) instead of a percentage. A caption describes the real pipeline (verified in `job_matching.py` / `job_search_service.py`).
- Job Details: definition list for facts, clearer "not in top 20" message.
- Customize Application: save errors shown, "Saved" resets after further edits, unsaved-edits notice, confirmation before switching versions or regenerating with unsaved edits, guarded version loading.
- Interview Prep: guarded version loading and duplicate-generate guard.
- Assistant: all conversation actions report errors, two-step delete confirmation, `role="log"` message list, auto-scroll, and the typed message is kept if sending fails.
- Dashboard: next-step navigation card (navigation only, no data), list markup, processing state shows a spinner and link to progress.
- Roadmap and Progress: explicit "not implemented in this version" empty states instead of placeholder wording.
- Profile: lint warning fixed, comma-separated hint, duplicate error removed.

**Design system (`src/App.css`, `index.css`, `profile.css`, `applications.css`):**
- Extended the existing `:root` tokens with `--body`, `--danger`, `--focus`, `--line-soft`, `--surface-2` and related values.
- Raised minimum UI text to 11–13 px and fixed sub-AA greys.
- Visible focus for every control type.
- Disabled cursor is `not-allowed` (was `wait`).
- Error and success notices get a coloured left border so meaning is not carried by colour alone.
- ✓ / ! icons replace the "OK"/"00" text.
- Sticky sidebar on desktop.
- Reduced motion is respected through the existing global rule; the spinner stops animating.

**Backend (minimal):**
- `app/services/auth.py` + `app/core/config.py`: the session cookie is `Secure` whenever `APP_ENV != development`, with a `SESSION_COOKIE_SECURE` override. Local development behaviour is unchanged.
- New test file `tests/test_session_cookie.py` (6 cases).

## 3. Verification (actually executed)

| Check | Result |
|---|---|
| `pytest -q` | **470 passed, 1 xfailed** (464 baseline + 6 new) |
| `npx tsc -b` | pass |
| `npm run lint` | **0 errors, 0 warnings** |
| `npm run build` | pass (JS 326 kB / 92.7 kB gzip; CSS 40.7 kB); no secrets in bundle |

Browser walkthrough against the local servers:

- Signed up a local test account. The empty dashboard showed the empty state.
- Dropped `notes.txt`: rejected client-side. Dropped a fake `.pdf`: backend 400 shown ("file extension does not match…"), one POST despite a double click, previous state kept.
- Uploaded a synthetic DOCX: it was processed and the results showed exactly the 8 skills in the file. After a page refresh the results were unchanged.
- Recommendations: 5 real matches. Job details: 68%, consistent with the list. Skill gap: 4/4 required skills, 76% readiness.
- Ended the session server-side, then navigated: returned to sign-in with an "expired" notice. A wrong password gave a generic error. Signing in again returned to the deep link.
- Stopped the backend: "We can't reach the server" with retry. Restarted it and pressed retry: the dashboard was restored.
- Cross-user check: a second account requesting the first account's resume, structured data, profile resumes and job matches got **404** on every one.
- No horizontal overflow on any of the 10 routes at 360, 375 and 768 px. Desktop checked at 1280 px.
- Keyboard: the skip link is the first focusable element, the file input is focusable, and no unlabeled controls were found on the resume page.

## 4. Not verified / known limitations

- **LLM-backed generation was not exercised.** `backend/.env` has an external OpenAI-compatible provider configured with a real key, so Customize generation, Interview Prep generation, mock-answer evaluation and Assistant replies were not triggered, to avoid sending data to the provider or using its quota. Their UI was checked in the pre-generation state only. The `tsc` build and existing backend tests cover their contracts.
- **No automated frontend tests exist in the repository.** All frontend verification above was manual or scripted in a browser, not a committed test suite.
- No automated accessibility scanner (axe or Lighthouse) is installed. Contrast was raised by design, not measured with a tool.
- Production deployment (HTTPS, SPA rewrite, `VITE_API_BASE_URL`, cookie domain) is documented in the README but not exercised on a host.
- Search relevance is shown as a raw similarity score. The backend formula is unchanged and can exceed 1.0 when many chunks of one opportunity match.
- Unused legacy prototype CSS classes (e.g. `.timeline`, `.score-ring`) remain in `App.css`. Removing them was not necessary for this pass.
- The learning roadmap remains unimplemented, and the UI says so plainly.
