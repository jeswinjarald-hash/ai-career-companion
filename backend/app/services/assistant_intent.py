"""Milestone 3.4 — deterministic intent detection for the Career Assistant.

Rule/keyword based, not LLM based: every intent this milestone supports has a
distinct enough vocabulary that a reliable classifier doesn't need a model call
(and a model call would mean an unpredictable, occasionally-wrong routing decision
for something that should be exact — "prepare me for the interview" must always
route to M3.3, never sometimes). The LLM is reserved for what it's actually good at:
wording the response naturally once the correct grounded data has already been
fetched (see `assistant_llm.py`).

Rules are checked in a fixed priority order (most specific first) and the first
match wins. `GENERAL_CAREER_CHAT` is the deterministic catch-all when nothing more
specific matches — never a classification failure.
"""

import re

_JOB_ID_PATTERN = re.compile(r"\bJOB-\d{3,6}\b", re.IGNORECASE)


def extract_job_ids(message: str) -> list[str]:
    """Returns real job-id-shaped tokens found in the message, uppercased to match
    the dataset's own `job_id` casing (e.g. "job-0035" -> "JOB-0035"). Order of first
    appearance is preserved; duplicates are removed. This never validates that the
    id actually exists in the dataset — that check happens later, against real data,
    in the context builder (an unrecognized id becomes a 404-style "job not found"
    response, never a silently accepted guess).
    """
    seen: list[str] = []
    for match in _JOB_ID_PATTERN.findall(message):
        upper = match.upper()
        if upper not in seen:
            seen.append(upper)
    return seen


_COMPARISON_KEYWORDS = ("compare", " vs ", " vs. ", " versus ")
_INTERVIEW_KEYWORDS = ("interview", "mock interview")
_COVER_LETTER_KEYWORDS = ("cover letter",)
_CUSTOMIZATION_KEYWORDS = ("customize", "tailor my resume", "tailor resume", "improve my resume", "resume for this job", "update my resume")
_SKILL_GAP_KEYWORDS = ("skill gap", "missing skills", "what am i missing", "what skills am i missing", "am i qualified", "my gaps", "skills am i lacking")
_LEARNING_KEYWORDS = ("what should i learn", "learn next", "study next", "revision plan", "what to study", "learning roadmap", "what should i study")
_MATCH_EXPLANATION_KEYWORDS = ("why does this", "why is this a match", "why does it match", "explain the match", "why does this role fit", "why does this job fit", "why is this role")
_DISCOVERY_KEYWORDS = ("which internships", "which jobs", "internships fit", "jobs fit", "recommend", "find jobs", "find internships", "search for", "suggest internships", "suggest jobs", "what internships")
_PROFILE_SUMMARY_KEYWORDS = ("my profile", "my strongest project", "my projects", "summarize my resume", "tell me about my resume", "about my background")
_NEXT_ACTION_KEYWORDS = ("what should i do next", "next step", "what now", "what should i do", "next best action")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_intent(message: str) -> tuple[str, float]:
    """Returns (intent, confidence). Pure text classification only — does not know
    about job ids, conversation history, or resume state; `detect_intent` layers
    that on top.
    """
    text = f" {message.strip().lower()} "

    if _contains_any(text, _COMPARISON_KEYWORDS):
        return "JOB_COMPARISON", 0.9
    if _contains_any(text, _INTERVIEW_KEYWORDS):
        return "INTERVIEW_PREP", 0.9
    if _contains_any(text, _COVER_LETTER_KEYWORDS):
        return "COVER_LETTER", 0.9
    if _contains_any(text, _CUSTOMIZATION_KEYWORDS):
        return "RESUME_CUSTOMIZATION", 0.85
    if _contains_any(text, _SKILL_GAP_KEYWORDS):
        return "SKILL_GAP", 0.85
    if _contains_any(text, _LEARNING_KEYWORDS):
        return "LEARNING_GUIDANCE", 0.8
    # Also catches the "why does JOB-0035 fit me?" phrasing (an explicit job id
    # instead of "this role"), which the fixed-phrase keyword list above doesn't.
    if _contains_any(text, _MATCH_EXPLANATION_KEYWORDS) or ("why" in text and ("fit" in text or "match" in text)):
        return "JOB_MATCH_EXPLANATION", 0.85
    if _contains_any(text, _DISCOVERY_KEYWORDS):
        return "JOB_DISCOVERY", 0.8
    if _contains_any(text, _PROFILE_SUMMARY_KEYWORDS):
        return "PROFILE_SUMMARY", 0.75
    if _contains_any(text, _NEXT_ACTION_KEYWORDS):
        return "NEXT_BEST_ACTION", 0.75
    return "GENERAL_CAREER_CHAT", 0.5


_JOB_CONTEXT_INTENTS = {
    "JOB_MATCH_EXPLANATION", "SKILL_GAP", "RESUME_CUSTOMIZATION",
    "COVER_LETTER", "INTERVIEW_PREP", "LEARNING_GUIDANCE",
}
_RESUME_CONTEXT_INTENTS = {
    "JOB_MATCH_EXPLANATION", "SKILL_GAP", "RESUME_CUSTOMIZATION", "COVER_LETTER",
    "INTERVIEW_PREP", "LEARNING_GUIDANCE", "PROFILE_SUMMARY", "JOB_DISCOVERY",
}


def detect_intent(message: str, active_job_id: str | None) -> dict:
    """The full detection result used by the orchestrator: classifies the message,
    extracts any explicit job id(s), and states which context this intent needs —
    never guessing an id that wasn't actually found in the message or the
    conversation's own remembered active job.
    """
    intent, confidence = classify_intent(message)
    job_ids = extract_job_ids(message)

    if intent == "JOB_COMPARISON":
        first_job_id = job_ids[0] if len(job_ids) >= 1 else active_job_id
        second_job_id = job_ids[1] if len(job_ids) >= 2 else (job_ids[0] if len(job_ids) == 1 and active_job_id else None)
        # With exactly one id in the message plus a remembered active job, compare
        # the new one against the one already being discussed.
        if len(job_ids) == 1 and active_job_id and active_job_id != job_ids[0]:
            first_job_id, second_job_id = active_job_id, job_ids[0]
        return {
            "intent": intent, "confidence": confidence,
            "job_id": first_job_id, "second_job_id": second_job_id,
            "requires_job_context": True, "requires_resume_context": False,
            "requires_second_job_context": True,
        }

    job_id = job_ids[0] if job_ids else active_job_id
    return {
        "intent": intent, "confidence": confidence,
        "job_id": job_id, "second_job_id": None,
        "requires_job_context": intent in _JOB_CONTEXT_INTENTS,
        "requires_resume_context": intent in _RESUME_CONTEXT_INTENTS,
        "requires_second_job_context": False,
    }
