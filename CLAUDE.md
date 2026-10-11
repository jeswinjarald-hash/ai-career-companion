# AI Career Companion — project instructions

## Architecture
- **Frontend:** React 19 + TypeScript (strict) + Vite 6, plain CSS (`src/App.css`, `src/index.css`, `src/profile.css`, `src/components/applications/applications.css`). No router library: URL ⇄ view mapping lives in `src/routing.ts` (`routeFromLocation`, `pathForView`); `src/App.tsx` drives the History API (`go`, `popstate`). Views split out of `App.tsx` live in `src/views/`. Job-scoped pages carry `?job=<id>`; `/jobs/<id>` and `/applications/<id>` are deep links.
- **Design system:** dark "Aurora Prism" theme (midnight base; blue `#4f8cff`, orchid `#b16cff`, teal `#43e6d0`). Tokens (colour, spacing, radius, shadow, type) are CSS custom properties in `src/index.css`; components in `src/App.css` (+ `profile.css`, `applications.css`) reuse the existing class names; `src/theme.css` (loaded last) adds glass surfaces, gradients and micro-interactions. Filled controls with white text use `--accent-solid`/`--danger-solid` (the bright `--accent` is for text and lines only). `src/components/Ambient.tsx` renders the decorative background (grid + three drifting glows): `aria-hidden`, `pointer-events: none`, below all content, `transform`-only animation, stopped under `prefers-reduced-motion`. System fonts only — no web-font or CDN requests. Icons: `src/components/icons.tsx`. Charts: `src/components/charts.tsx` (`MeterChart` — a real `<table>` with decorative bars; `ScoreRing` — one real 0–100 value; `null` is "Not available", never 0). No UI dependency beyond React.
- **Pointer lighting:** one hook, `src/components/usePointerLight.ts` (used by `Ambient`), owns the only pointer listener: it moves the global spotlight (`transform`) and sets card-local `--sx/--sy` + `.is-lit` on the innermost `.card` under the mouse, at most one `requestAnimationFrame` pending, no React state. Active only for `(hover: hover) and (pointer: fine)` without reduced motion; touch is ignored and no event is prevented. Card light/border styles: `.card::before/::after` in `src/theme.css` (clipped to the card; `:has(:focus-visible)` gives the keyboard equivalent). Do not add other global pointer listeners. Tested by `e2e/lighting.spec.ts`.
- **Contrast:** axe cannot evaluate text over gradient/translucent surfaces, so `e2e/contrast.spec.ts` measures rendered pixels (method in `e2e/support/contrast.ts`) on every screen. Keep it passing when changing colours or surfaces.
- **Background layer:** `src/components/Ambient.tsx` (aria-hidden, pointer-events none) holds the glows, the skill graph canvas and the pointer spotlights. `src/components/backgroundRuntime.ts` holds the shared pieces:
  - the single animation-frame scheduler (`requestTick`/`cancelTick`);
  - the pointer feed, published only by `usePointerLight` (the one pointer listener), including the hovered `[data-graph-magnet]` card;
  - the single shared scroll listener (`subscribeScroll`);
  - the skills store and the scene store.

  Sources of graph data:
  - `App` publishes skills with `graphSkills()` (`src/lib/skillGraphData.ts`): the processed resume's extracted skills, then profile skills. It publishes none when the user is signed out. Never substitute demo skills.
  - `App` publishes the route scene with `sceneModeForView()` (`src/lib/skillGraphScene.ts`), plus whether a resume upload or analysis is in flight.
  - `SkillsView` publishes gap labels from a real skill-gap analysis (`gapSkillsFromAnalysis`).
  - `AssistantView` publishes its real `sending` state.

  `src/components/skillGraphEngine.ts` (Canvas 2D; physics in `src/lib/skillGraphPhysics.ts`; formations and edges in `src/lib/skillGraphScene.ts`) never remounts on navigation. A route change starts a ~1.2 s eased transition toward that mode's formation. Each node gets the nearest formation slot, computed once per transition. Limits:
  - nodes: 24 on desktop, 10 below 768 px or without a fine pointer;
  - device pixel ratio: 1.5;
  - frame rate: 30 fps;
  - constellation lines: per node and in total, opacity ≤ `MAX_LINK_ALPHA`;
  - scroll parallax: ≤ `PARALLAX.max`.

  Placement and matching (pure geometry in `src/lib/skillGraphSpace.ts`), run on a transition, a data or size change, and 250 ms after the layout settles — never per frame:
  - Node identity, hue and depth come from the label (`nodeId`), not its position in the list.
  - Each node takes the nearest formation slot; pairwise swaps that shorten total travel then remove blocking paths.
  - Each slot moves into nearby open background where that capsule fits (`placeInOpenSpace`, up to `PLACEMENT_REACH`).
  - Overlapping targets are relaxed apart (`separateTargets`).
  - A rate-limited re-match resolves head-on jams.

  Surfaces and anchors:
  - Heading text wrappers are measured by their text's bounds, not the full-width block.
  - `[data-graph-keep-clear]` zones (drop zone, assistant composer) never have anything drawn behind them.
  - `[data-graph-anchor]` (drop zone, assistant panel) gives a formation the real surface to lay out around.

  Labels and lines:
  - A label shows only while the whole capsule has clearance from every surface and the viewport edge, with hysteresis; otherwise the capsule is a label-free outline, crossfaded.
  - Lines are trimmed to the exact pill outlines (`trimToCapsules`) and drawn only between two labelled capsules, never across a surface.
  - Edges are decorative proximity lines: the API has no skill-relationship data, so never present them as relationships.

  Sleep and modes:
  - The loop sleeps when `shouldSleep` says every source is quiet. Settling is judged by actual movement; a jammed node's residual velocity is zeroed at sleep, and a resting pointer does not keep the loop awake.
  - The loop pauses in hidden tabs.
  - With reduced motion or a coarse pointer the engine draws one static, placed composition per route.

  The dev snapshot (`window.__skillGraph`, dev builds only) exposes nodes, edges, targets and the last sleep signals for the e2e tests. Tests: `tests/unit/skillGraph.test.ts`, `tests/unit/skillGraphScene.test.ts`, `tests/unit/skillGraphSpace.test.ts`, `e2e/skill-graph.spec.ts`, `e2e/skill-graph-routes.spec.ts`.
- **Derived data:** every dashboard/chart value comes from `src/lib/insights.ts` (pure, unit-tested: dashboard state, resume section coverage, skill-gap readiness rows, application status rows, match-score definition) or directly from an API field. Document the source and definition of any new metric there.
- **API access:** every feature service in `src/services/*.ts` calls the backend through `apiFetch` in `src/config/api.ts` (credentialed fetch; a 401 dispatches `SESSION_EXPIRED_EVENT`, which `App` turns into a return to sign-in). `authService` uses raw fetch because a 401 there means wrong credentials. Errors are made readable with `apiDetailMessage` (FastAPI 422 lists, generic text for 5xx).
- **Backend:** FastAPI + SQLAlchemy + SQLite (`backend/app`), Sentence-Transformers + FAISS retrieval (`backend/data/vector_store`), optional OpenAI-compatible LLM (`app/services/llm_provider.py`, selected by `LLM_PROVIDER`; `none` = deterministic pipeline). Entry point `backend/app/main.py`. Settings come from `backend/.env` via pydantic-settings; process environment variables override it.
- **Auth:** HttpOnly `ai_career_session` cookie backed by a DB session table. Protected routes use `Depends(require_current_user)` plus ownership checks (`get_owned_profile`, `get_owned_resume`). Never weaken these.
- **Resume pipeline (UI):** upload → `extract-text` → `detect-sections` → `structure` → `candidate-context`; the active resume is always the latest one returned by `GET /api/profiles/{id}/resumes`. No browser storage holds account data.

## Commands (Windows, from the repo root unless noted)
- Frontend dev: `npm run dev` (http://localhost:5173, API at `VITE_API_BASE_URL`, default http://localhost:8000)
- Backend dev (from `backend/`): `..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- Type check: `npx tsc -b` (app, vite config, e2e, and the API contract check)
- Lint: `npm run lint`
- Backend tests (from `backend/`): `..\.venv\Scripts\python.exe -m pytest -q` (`backend/pytest.ini` limits collection to `tests/`)
- Unit tests (pure logic in `src/routing.ts`, `src/lib/`): `npm run test:unit` (Playwright runner, no browser; tests in `tests/unit/`)
- Browser tests: `npm run test:e2e` (Playwright, installed Chrome via `channel: 'chrome'`; set `PW_CHANNEL=chromium` if the bundled browser is installed). Type passwords only with `fillSecret()` (`e2e/support/fixtures.ts`): `locator.fill()` records the typed text in step titles. Traces (`PW_TRACE=1`) and the HTML report (`PW_HTML=1`) are opt-in for local debugging because they keep step and request data — delete `e2e/.tmp` afterwards. `e2e/harness/` holds test-only pages served by the e2e Vite server (not build inputs).
- API types: `npm run api:types` regenerates `src/api/generated/`; `npm run api:check` fails if they are stale. `src/api/contract.check.ts` makes `tsc` fail when backend schemas and the hand-written service types diverge.
- Build: `npm run build` writes `dist/`. To verify a build without touching `dist/`, use `npx vite build --outDir <temp dir> --emptyOutDir`.

## Toolchain
- Node 18.19 / npm 10.2. Node 18 is end-of-life; `@playwright/test` is pinned to 1.61.1, the last release supporting it — upgrade Node to 20+ before unpinning.
- Python 3.12 virtualenv at `.venv` (`backend/requirements.txt`).
- `openapi-typescript` is pinned exactly. The header of `src/api/generated/schema.d.ts` records the Python, FastAPI, Pydantic and openapi-typescript versions it was generated with; `npm run api:check` reports a toolchain mismatch separately from API drift. Regenerate only with matching versions, and review the diff.

## Rules
- **No mock or fabricated data in the application.** Every number, score, chart, status or list shown must come from an API response or persisted value. No fake progress percentages, random scores or placeholder activity; unimplemented features say so plainly (see Learning Roadmap).
- **Preserve API contracts.** Do not change backend routes, schemas or the database schema to suit the UI without explicit approval. After any backend schema change run `npm run api:types` and `npx tsc -b`.
- **Test isolation (enforced, not just configured).**
  - pytest: before the app is imported, `backend/tests/conftest.py` sets a per-session temporary database and resume store, `LLM_PROVIDER=none`, `EMBEDDING_ALLOW_DOWNLOAD=false` and Hugging Face offline mode; at session end it restores the environment and deletes that directory. A Python audit hook refuses, for the whole test process, any open or listing of `backend/data/ai_career_companion.db` or `backend/data/resumes/` (including `sqlite3.connect`) and any non-loopback network connection. `tests/test_isolation.py` proves each guard fires. Per-test `tmp_path` directories are managed by pytest (it keeps the last 3 runs).
  - Playwright: the suite starts its own backend (`e2e/support/backend_server.py`, port 8100) and Vite (port 5174) and never reuses the developer's servers or sessions. The backend uses a throwaway database under `e2e/.tmp/`, the same offline settings and an equivalent audit hook, and refuses to start unless a self-test confirms them. In the browser every request to a non-local host is blocked, and the network guard (`e2e/support/fixtures.ts`, tested by `e2e/guard.spec.ts`) fails a test on page errors, console errors, failed requests, missing JS/CSS assets and unexpected HTTP errors. Its only exemptions: a logout that got its 204 but is reported as `ERR_ABORTED`, and the script local Kaspersky web protection injects into pages (still blocked).
  - Test data is synthetic only: `e2e/support/make_synthetic_resume.py` (DOCX) and `backend/tests/pdf_line_fixture.py` (PDF). Never read, copy or print files from the real resume store, and never point tests at a live LLM provider.
- **Secrets.** Never print or commit values from `backend/.env` (it holds a real LLM key). Report only whether a setting is present.
- **Git.** Work on a branch off `develop`. Never commit or push without the user's approval; never force-push, reset, or delete untracked files (`docs/FINAL_TECHNICAL_DOCUMENTATION*`, `.claude/`). Do not delete `dist/`, the virtualenvs, or generated data without approval.
- **Verification.** Before calling work done: `npx tsc -b`, `npm run lint`, `npm run api:check`, `npm run test:unit`, backend pytest, `npm run test:e2e`, and a build to a temp directory. Report results exactly, including failures and anything not verified.
