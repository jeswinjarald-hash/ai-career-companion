# Milestone 3.4 — Conversational Career Assistant

A single conversational assistant that answers real career questions by routing to
M2/M3.1/M3.2/M3.3's own service functions and synthesizing their real outputs into
natural conversational wording. M3.4 is an **orchestration layer only** — it
introduces no new scoring, matching, generation, or grounding logic of its own; every
personalized fact it states comes from a service call this project already built and
already tested.

## Architecture

```
User message
  -> deterministic intent detection (app/services/assistant_intent.py)
  -> context resolution: real job/resume/profile data, ids re-validated, never
     trusted from the frontend or guessed (app/services/assistant_context.py)
  -> missing-context check: if required job/resume context is absent, a concise
     follow-up is returned immediately — no service call is attempted
  -> per-intent handler: calls M2/M3.1/M3.2/M3.3's own functions directly and
     builds a deterministic, fully grounded baseline answer (app/services/
     assistant_handlers.py) <- always computed, the fallback
  -> optional grounded LLM synthesis: rewords the baseline answer using the same
     provider abstraction and repair-once-then-fallback pattern M3.2/M3.3 use
     (app/services/assistant_llm.py)
  -> persisted conversation turn (app/services/assistant_service.py)
  -> frontend render: message list + suggested action buttons + AI Enhanced /
     Grounded Fallback badge
```

## Reused from M1 / M2 / M3.1 / M3.2 / M3.3 (not rebuilt)

- `app.services.job_matching.match_jobs_for_resume` (M2 job discovery/match).
- `app.services.interview_evidence.best_effort_m2_match` (M2's own best-effort
  lookup, reused directly rather than re-implemented a third time).
- `app.services.skill_gap_service.analyze_skill_gap` / `get_persisted_skill_gap`
  (M3.1 — never re-scored; every skill-gap claim the assistant makes is M3.1's own
  computed `strengths`/`critical_gaps`/`partial_gaps`/`preferred_gaps`).
- `app.services.resume_customization_service.generate_customization` /
  `list_customizations` / `get_customization` (M3.2 — the assistant reuses an
  existing, non-stale tailored resume/cover letter if one exists, and only calls
  `generate_customization` when the student explicitly asks and none exists yet).
- `app.services.interview_prep_service.generate_interview_preparation` /
  `list_interview_preparations` / `get_interview_preparation` (M3.3 — same
  reuse-or-generate pattern).
- `app.services.llm_provider` (`LLMProvider`, `NullLLMProvider`,
  `OpenAICompatibleProvider`, `get_llm_provider`) — the exact M3.2/M3.3 provider
  abstraction, zero new code.
- `app.services.customization_validator.check_fabrication` — extended (not forked)
  with one new function, exactly as M3.3 already extended it once.
- `app.services.job_dataset_service.load_job_postings`,
  `app.services.resume.list_profile_resumes`, `app.services.auth.require_current_user`.
- Frontend: existing CSS classes (`.card`, `.assistant-layout`, `.message`,
  `.skill-status`, `.error-notice`, ...), `GENERATION_LABEL`/`GENERATION_TONE`
  reused directly from `App.tsx`, and the existing typed-fetch service pattern.

## Intent detection (`assistant_intent.py`)

Deterministic, rule/keyword based — not an LLM call. Every intent this milestone
supports (`JOB_DISCOVERY`, `JOB_MATCH_EXPLANATION`, `SKILL_GAP`,
`RESUME_CUSTOMIZATION`, `COVER_LETTER`, `INTERVIEW_PREP`, `LEARNING_GUIDANCE`,
`JOB_COMPARISON`, `PROFILE_SUMMARY`, `NEXT_BEST_ACTION`, `GENERAL_CAREER_CHAT`) has
a distinct enough vocabulary that a keyword classifier routes it reliably and
predictably — "prepare me for the interview" must always route to M3.3, never
sometimes, which a model call couldn't guarantee. The LLM is reserved for wording
the response naturally once the correct grounded data has already been fetched.

`extract_job_ids` finds real `JOB-####`-shaped tokens in the message (case-
insensitive, deduplicated) — never validated here; an unrecognized id is only
discovered later, against the real dataset, in context resolution. `detect_intent`
combines the classified intent with the conversation's remembered `active_job_id`:
an explicit id in the message always wins, otherwise the remembered job carries
over, otherwise the intent is left unresolved (never guessed). Comparison intents
need two ids: one explicit id plus a remembered active job compares the new one
against the one already being discussed; zero or one id with no active job leaves
both unresolved, triggering a follow-up rather than a guess.

## Context resolution (`assistant_context.py`)

`resolve_context` re-validates every id against real data: `get_job` checks the
actual dataset (an unknown id becomes `job_not_found`, never a silent guess);
`latest_resume_for_user` uses the exact same "most recently created resume for this
user" convention the frontend's own `activeResumeId` already uses, so the assistant
never introduces a second, different notion of "the current resume". Only the
minimum needed is fetched — `resolve_context` never queries M3.1/M3.2/M3.3's own
generation functions; those run only inside the handler that actually needs them,
per the intent (`load context based on intent`, not "load everything every time").

## Per-intent handlers (`assistant_handlers.py`)

Each handler returns a `HandlerResult`: the deterministic, fully grounded message
(always computed — the fallback), a compact `facts` payload (the only data the
optional LLM synthesis step may reference), the suggested action buttons, and which
services were consulted (`context_used`). None of these functions score, match, or
generate anything themselves — they call the milestone's own service and format its
real output.

| Intent | Routes to |
| --- | --- |
| `JOB_DISCOVERY` | M2 `match_jobs_for_resume` |
| `JOB_MATCH_EXPLANATION` | M2 best-effort match + M3.1 `analyze_skill_gap` |
| `SKILL_GAP` | M3.1 `analyze_skill_gap` |
| `RESUME_CUSTOMIZATION` / `COVER_LETTER` | M3.2 `generate_customization` (reused if a non-stale version already exists) |
| `INTERVIEW_PREP` | M3.3 `generate_interview_preparation` (reused if a non-stale version already exists) |
| `LEARNING_GUIDANCE` | M3.1's own gap priorities (critical -> partial -> preferred), not a duplicate of M3.3's revision-plan builder |
| `JOB_COMPARISON` | Two real job postings, factual only; enriched with M3.1 for both jobs if a resume exists |
| `PROFILE_SUMMARY` | The structured resume + profile directly — no job needed |
| `NEXT_BEST_ACTION` | A fully deterministic priority chain over real persisted state (resume -> structured -> skill gap -> customization -> interview prep) |
| `GENERAL_CAREER_CHAT` | No service call — a fixed, honest "here's what I can help with" message |

`RESUME_CUSTOMIZATION`/`COVER_LETTER`/`INTERVIEW_PREP` never call the underlying
milestone's generator on *every* message — `_get_or_generate_customization`/
`_get_or_generate_interview_prep` check for an existing, non-stale version first
and reuse it (avoiding a redundant M3.2/M3.3-level LLM call on every follow-up
question about the same job).

## Grounding: three validation tiers, not two

M3.3 introduced a two-tier distinction (`check_fabrication` strict vs.
`check_fabrication_patterns` relaxed-on-keywords). Building M3.4 surfaced a case
neither tier covered: **a real, already-computed percentage is not a fabrication.**
A skill-gap readiness percentage or a job-match percentage is grounded — it comes
straight from M3.1/M2's own scoring — but `check_fabrication`'s metric-check
(`\d+%`) is deliberately blunt (write for M3.2, where a resume bullet stating any
percentage is inherently suspect), and would incorrectly strip a sentence as
"simple" as "your readiness is 78%".

The fix (found via smoke testing before the formal test suite was even written):
`check_fabrication_patterns_excluding_metrics` — leadership/years-of-experience
checks only, added to `customization_validator.py` as a third, even-narrower tier,
purely additive to the existing two. `assistant_handlers.py`'s `HandlerResult.
grounding_mode` selects `"scored"` for every intent whose `facts` legitimately
include a real percentage and/or a named skill gap (`JOB_DISCOVERY`,
`JOB_MATCH_EXPLANATION`, `SKILL_GAP`, `LEARNING_GUIDANCE`, `JOB_COMPARISON`,
`INTERVIEW_PREP`), and `"strict"` (the full check, unchanged) for the rest
(`RESUME_CUSTOMIZATION`, `COVER_LETTER`, `PROFILE_SUMMARY`, `NEXT_BEST_ACTION`,
`GENERAL_CAREER_CHAT`), whose facts never legitimately need either relaxation. An
invented leadership/team-size or years-of-experience claim is still never
legitimate in any tier — only a real, already-known number or gap-skill name is
ever permitted through.

`unsupported_terms` (the set of missing-skill names) is still passed and still
matters even in `"scored"` mode conceptually — a `"scored"` intent's own baseline
text is already correct-by-construction (it's built directly from real gap data,
same discipline as M3.3), so the check exists purely to catch the LLM synthesis
step introducing something the baseline didn't say.

## LLM synthesis (`assistant_llm.py`)

Mirrors `interview_llm.py`/`customization_llm.py` exactly: the model receives the
intent, the `facts` object (the only real data it may reference), the already-
correct `baseline_answer`, the student's message, and the last 6 conversation turns
for continuity — never a free-form "answer this" prompt. The system prompt states
explicitly: reword/connect the baseline to the conversation, but never add a fact,
invent a score, or contradict the baseline; never state or imply the student has
demonstrated an `unsupported_skills_do_not_use` entry; never invent a metric not in
`facts`; **never declare one job "better" than another** — only state which one
aligns with more currently-demonstrated requirements, and only if `facts` shows
that. Repair-once-then-fallback, identical control flow to M3.2/M3.3: one repair
attempt on a validation failure (shown the specific violation), a provider-level
failure (timeout, network error) skips repair entirely, and any remaining failure
returns `None` — the caller then ships `baseline_answer` as-is, tagged
`deterministic_fallback`.

**Important, and demonstrated live**: the "AI Enhanced" / "Grounded Fallback" badge
on a chat message reflects *this conversational synthesis step*, independent of
whatever generation mode the underlying M3.2 customization or M3.3 interview prep
artifact was itself created with (visible separately on those pages). Asking the
assistant to "prepare me for the interview" for a job that already has a persisted
interview prep reuses that record as-is (correct fact, no new M3.3 generation);
the assistant's own message about it can still be "AI Enhanced" if the *assistant's*
LLM call to word that summary succeeded, even though no new interview-prep LLM
call happened at all.

## Deterministic fallback

Every handler's `message` field is a complete, grounded answer on its own — never a
placeholder waiting for the LLM. If no provider is configured, or it fails, times
out, or returns something that fails validation (even after one repair attempt),
the deterministic message ships unchanged, tagged `deterministic_fallback`. Live-
verified: with `LLM_PROVIDER=none`, "What skills am I missing for JOB-0035?" still
returned "For FastAPI Intern at QuantumLeaf Technologies, your readiness is 80%.
You meet all required skills. Preferred (non-mandatory) gaps: Flask, Docker,
Agile." — a complete, useful, fully grounded answer, badge correctly showing
**"Grounded Fallback"**.

## Conversation persistence, context retention, and staleness

New tables (`app/models/conversation.py`): `conversations` (`user_id`, `title`,
`active_job_id`, `active_resume_id`, timestamps) and `conversation_messages`
(`conversation_id`, `role`, `content`, `intent`, `metadata_json`, `created_at`).
`metadata_json` holds only what the frontend needs to render the turn (suggested
actions, the job/resume ids actually used, which context sources were consulted,
generation metadata) — never a provider secret, hidden chain-of-thought, or the
full internal prompt.

**Job context retention**: `conversation.active_job_id` is updated after every turn
that resolved a job — but *only* when one was actually resolved; an intent that
didn't need a job (e.g. `GENERAL_CAREER_CHAT` with no job mentioned) never clears a
previously established one. This means even mentioning a job id in passing (*"tell
me about JOB-0035"* — itself `GENERAL_CAREER_CHAT`, since it names no specific
supported action) establishes it as the active job for every subsequent turn, live-
verified across a 7-turn conversation that never repeated `JOB-0035` again after the
first mention.

**Resume staleness**: context resolution always re-fetches the user's actual latest
resume (never trusts a stored `active_resume_id`) — if it differs from what the
conversation last used, the response includes a plain-language notice ("I'm now
using your most recently uploaded resume...") and the conversation's
`active_resume_id` is updated to match, rather than silently continuing to reason
about an outdated resume. Similarly, if the M3.1 skill-gap data behind a response is
itself stale (the resume changed since that analysis was generated — M3.1's own
`stale` flag, not re-derived), a notice is appended rather than silently presenting
outdated personalized analysis as current.

## Job comparison (factual only)

`handle_job_comparison` states only comparable facts — location/mode, required/
preferred skills, and (if a resume exists) each job's independently-computed M3.1
readiness percentage and required-skills-demonstrated count — and never an
evaluative "X is better than Y". The LLM synthesis system prompt repeats this
constraint explicitly. Live-verified: comparing `JOB-0035` and `JOB-0036` produced
a clean side-by-side factual comparison with no superiority claim anywhere in the
"AI Enhanced" wording.

## Next best action (fully deterministic)

`handle_next_best_action` never calls the LLM for its *decision* — the priority
chain (no resume -> upload; not processed -> process; no target job -> explore
recommendations; job selected but no skill gap -> analyze; gaps exist -> review
learning; ready -> customize; customized -> prepare for interview) is a plain
if/elif chain over real persisted state, so the recommended next step can never be
a hallucinated stage. The LLM (when available) only rewords the resulting message.

## What the assistant deliberately does *not* do: resolve ordinal references

Live validation followed the spec's own example flow — *"Which internships fit my
resume?"* then *"Why does the first one fit me?"*. The assistant does **not**
resolve "the first one" to a specific job id; it responds with a concise follow-up
asking which internship to use. This is a deliberate consequence of the anti-
guessing requirement ("if required context is missing, ask a concise follow-up
instead of guessing"): "the first one" is not an id the message or the remembered
`active_job_id` actually contains, and silently picking the top result from a
*previous* turn's now-stale result list would be exactly the kind of guess this
milestone is built to avoid. Naming the job explicitly (or clicking its "View
{job}" action button, which does set the active job) continues the conversation
normally. See Known limitations.

## API

```
POST   /api/career-assistant/conversations
GET    /api/career-assistant/conversations
GET    /api/career-assistant/conversations/{id}
POST   /api/career-assistant/conversations/{id}/messages
DELETE /api/career-assistant/conversations/{id}
```

Every endpoint requires authentication and verifies `conversation.user_id ==
current_user.id` before touching a conversation (`404`, matching the rest of the
codebase's ownership convention) — a user can never read, message, or delete
another user's conversation. `POST .../messages` never trusts an `id` from the
frontend without re-resolving it against real data (see Context resolution above);
the frontend's optional `job_id` hint is only ever a fallback used when the message
itself names no job and the conversation has no remembered one yet.

## Frontend

`src/services/assistantService.ts` follows the existing typed-fetch pattern. The
existing **"AI Career Assistant"** nav entry now opens the real implementation
(replacing the milestone-3.3-era placeholder that unconditionally responded "AI
guidance is planned for a later milestone").

The page shows: a conversation sidebar (new conversation, list with title/message
count/active job, delete), a current-context indicator (resolved job title, resume
connection status), the message list (user/assistant bubbles, an **AI Enhanced /
Grounded Fallback** badge per assistant turn, multi-line content preserved for
cover-letter previews and multi-part answers), suggested action buttons per
assistant message that navigate to the real existing page for that action (Job
Details, Skill Gap Analysis, Customize Application, Interview Preparation, Career
Recommendations, Resume Analyzer/Results) — never a duplicate chat-embedded copy of
those pages — and context-aware starter prompts (no hardcoded job names) shown both
in the empty state and in a persistent "Try asking" list. Loading/error states never
leave the UI stuck: a "Thinking..." indicator shows while a message is in flight,
and any failure surfaces as a real `error-notice`.

## Tests

- `backend/tests/test_assistant_intent.py` (15 tests) — pure-function unit tests for
  every supported intent's classification, job-id extraction/deduplication,
  comparison requiring two ids (with active-job fallback), and active-job carry-over
  vs. an explicit id overriding it.
- `backend/tests/test_assistant_service.py` (19 tests) — routing into M2/M3.1/M3.2/
  M3.3 (verified via real side effects: a `SkillGap`/`ApplicationCustomization`/
  `InterviewPreparation` row actually persisted, not just a plausible-looking
  message); job context retention across a 4-turn conversation without repeating an
  id; missing-job and missing-resume follow-ups; missing skills never claimed as
  demonstrated (a genuinely-absent required skill, verified absent from skills
  *and* experience/project text so M3.1 has no fuzzy evidence to fall back on);
  a hallucinated LLM claim ("5 years of professional experience with REST APIs")
  rejected and falls back; factual job comparison with no "is better" language;
  comparison with no ids identified stays unresolved; provider timeout falls back
  without wasting a repair call; a valid LLM response yields `mode == "llm"`;
  conversation/message persistence and ordering; ownership enforcement (`LookupError`
  for another user's conversation); stale-resume auto-refresh with the refresh
  notice; suggested-action metadata shape; conversation list message counts. Every
  LLM-path test injects a fake provider — no live Gemini calls.
- `backend/tests/test_assistant_api.py` (8 tests) — authentication required on
  every endpoint; conversation create/list/get; unknown conversation `404`s;
  cross-user ownership isolation (a second user cannot read, message, or delete
  another user's conversation); a full send-message round trip through the real
  API; prior messages load in correct order; delete conversation; empty content is
  rejected (`422`). `get_llm_provider` is monkeypatched to `NullLLMProvider` here
  for the same reason `test_interview_prep_api.py` already does it — this
  repository's real `backend/.env` carries a live Gemini key for manual validation,
  and `get_settings()` is process-wide `lru_cache`d.

Full backend regression (`pytest -q`, 295 tests across M1/M2/M3.1/M3.2/M3.3/M3.4):
**295 passed**. `npm run build` and `npm run lint`: clean (0 TypeScript errors, 0
new lint issues — the sole warning is the same pre-existing, unrelated one in
`ProfileView` noted in the M3.3 documentation).

## Live E2E validation (2026-09-24)

Performed against the same real test account/resume/Gemini configuration used for
M3.3's live validation (so this session's real interview-prep/customization records
already existed, exercising the reuse-not-regenerate path for real):

login (existing session) -> AI Career Assistant -> **"Which internships fit my
resume?"** -> **"Why does the first one fit me?"** (correctly asked a follow-up
rather than guessing — see above) -> **"Why does JOB-0035 fit me?"** -> **"What
skills am I missing?"** -> **"What should I learn first?"** -> **"Customize my
application."** -> **"Prepare me for the interview."** -> **"Compare JOB-0035 and
JOB-0036"** -> provider disabled, re-asked the skill-gap question -> provider
restored -> full-page refresh.

- Every intent in the sequence classified correctly and routed to the correct
  underlying milestone (confirmed both by the response content and, for
  `RESUME_CUSTOMIZATION`/`INTERVIEW_PREP`, by the real persisted version numbers
  shown in the response text).
- **Job context never had to be repeated** after the first explicit mention of
  `JOB-0035` — four subsequent turns ("why does this fit", "what am I missing",
  "what should I learn", "customize my application", "prepare me for the
  interview") all resolved it from the conversation's remembered `active_job_id`.
- **Real Gemini synthesis succeeded** on every turn until the provider was
  deliberately disabled — badge correctly showed **"AI Enhanced"** throughout, with
  natural, varied wording that never contradicted or added to the grounded facts.
- **Grounded Fallback, live**: with `LLM_PROVIDER=none` and the backend restarted,
  re-asking "What skills am I missing for JOB-0035?" returned the badge
  **"Grounded Fallback"** with the identical grounded content (readiness 80%, all
  required skills met, preferred gaps Flask/Docker/Agile) — a complete, useful
  answer with no service degradation, just no AI-polished wording.
- **Conversation persistence, live**: a full page refresh (new page load, re-
  fetching from the backend, no client-side cache) reproduced the entire multi-turn
  conversation exactly, including both the AI Enhanced and Grounded Fallback turns.
- **Job comparison, live**: factual side-by-side comparison of `JOB-0035` and
  `JOB-0036` (both requiring Python/SQL/REST APIs/Git; readiness 80% vs. 78%;
  4/4 required skills demonstrated for both) — no "better" language anywhere in the
  AI-synthesized wording.
- `.env` API-key hygiene re-verified (`git check-ignore`, `git grep`) both before
  and after this session's two provider-toggling `.env` edits.

## Manual grounding audit (2026-09-24)

Ten claims audited against real stored/computed data from the live session above —
covering the spec's minimums (>=5 personalized, >=3 skill-gap, >=3 job-match
explanation, >=2 interview reference, >=1 comparison):

1. "You already demonstrate Python, SQL, REST APIs, Git, and FastAPI" — all five
   terms verified present in the real resume's skills/experience/project text.
2. "your readiness is 80%. You meet all required skills." — traces to M3.1's own
   computed `overall_readiness` and empty `critical_gaps`, not re-derived here.
3. "Preferred (non-mandatory) gaps: Flask, Docker, Agile." — traces to M3.1's
   `preferred_gaps`; the real job's preferred skills minus what the resume shows;
   correctly phrased as gaps, never as demonstrated.
4. "Flask (low priority): Build or extend a REST API using Flask..." — traces
   verbatim to M3.1's own `GapItem.recommendation` text for Flask.
5. "Docker (low priority): Containerize one of your existing backend projects
   with Docker..." — traces verbatim to M3.1's own recommendation for Docker.
6. Resume-customization summary quote — traces to the real, already-validated
   M3.2 `tailored_resume.summary` for this exact job/resume pair.
7. "13 technical, 2 resume, 5 project, 5 role, 6 hr, and 3 skill_gap questions" —
   matches the real, already-generated M3.3 `InterviewPreparation`'s actual
   question-category counts for this job/resume pair.
8. "top revision priority is the Career Companion API... JWT authentication and
   automated pytest test suites" — traces verbatim to the real project's own
   `raw_text` and the real M3.3 revision-plan reason.
9. Job comparison required/preferred skills for both `JOB-0035` and `JOB-0036` —
   verified against the real `JobPosting` records in the dataset.
10. Job comparison readiness (80% vs. 78%) and required-skills-demonstrated
    (4/4 vs. 4/4) — traces to two independent, real M3.1 `analyze_skill_gap` calls,
    one per job; no evaluative "better" language present anywhere in the response.

No unsupported claim was found in any audited turn.

## Known limitations

- **Ordinal references ("the first one", "that one") are not resolved** — see the
  dedicated section above. This is a deliberate anti-guessing choice, not an
  oversight: resolving "the first one" would require trusting that the previous
  turn's result ordering is still what the user means, which the spec's own
  "ask a concise follow-up instead of guessing" rule explicitly disfavors. A user
  can always name the job explicitly or click a "View {job}" action button instead.
- **Intent detection is keyword-based, not ML-based** — reliable for the vocabulary
  this milestone's spec enumerates, but a sufficiently unusual phrasing of a
  supported intent can fall through to `GENERAL_CAREER_CHAT` rather than the
  specific intent (e.g. a message with none of the recognized comparison/interview/
  cover-letter/customization/skill-gap/learning keywords, and no "why...fit/match"
  pattern, is treated as general chat even if a human reader would infer a more
  specific intent from context). No LLM-based classification fallback was added on
  top, since the deterministic rules already cover every intent/example utterance
  the spec enumerates, and adding a second, non-deterministic classification path
  would reintroduce exactly the "unpredictable routing" problem the deterministic-
  first design was chosen to avoid.
- **No persisted "session" concept beyond the conversation itself** — each
  conversation's `active_job_id`/`active_resume_id` are its own memory; there is no
  cross-conversation "the user's current focus" beyond what the frontend's own
  `selectedJobId`/`activeResumeId` state (passed as an optional hint on each new
  conversation/message) already provides.
- **`JOB_DISCOVERY` requires a resume** — "which internships fit me" is treated as
  inherently personalized (M2's own recommendation output), so a resume-less
  student is asked to upload one rather than being offered an un-personalized
  generic search; free-text semantic search (`app.services.job_search_service.
  search_jobs`) remains available via the existing Career Recommendations page's
  own search box, unchanged by this milestone.
