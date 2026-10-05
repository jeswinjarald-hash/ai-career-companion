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

# Words that only express "show me opportunities" (verbs, pronouns, filler, generic
# opportunity nouns) — whatever is left after removing them is the area the student
# actually asked about. Deliberately generic: no domain or skill names live here.
_DISCOVERY_FILLER = frozenset(
    "a an the any some all of in on at for to with from and or me my i i'm im we us you your please can could would will "
    "do does is are there what which who where how find search show list give suggest recommend recommended looking look "
    "want need get see good best top new more other based fit fits fitting match matches matching suit suits suitable "
    "resume cv profile background skills experience opportunity opportunities job jobs role roles position positions "
    "opening openings vacancy vacancies career careers work".split()
)
# Opportunity-type words narrow a request but are not an area on their own.
_OPPORTUNITY_TYPE_WORDS = frozenset(
    "internship internships intern interns entry level entry-level graduate graduates grad trainee trainees "
    "traineeship apprenticeship apprenticeships apprentice program programs programme programmes junior fresher freshers".split()
)
_WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#./-]*")


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
_DISCOVERY_KEYWORDS = (
    "which internships", "which jobs", "which roles", "which opportunities", "internships fit", "jobs fit",
    "roles fit", "opportunities fit", "recommend", "find jobs", "find internships", "find opportunities",
    "find entry level", "find entry-level", "find graduate", "find trainee", "search for", "suggest internships",
    "suggest jobs", "suggest opportunities", "suggest roles", "what internships", "what opportunities",
    "entry level jobs", "entry-level jobs", "graduate roles", "graduate jobs", "trainee roles", "trainee programs",
    "apprenticeship", "opportunities match my resume", "opportunities fit my resume",
)
_PROFILE_SUMMARY_KEYWORDS = ("my profile", "my strongest project", "my projects", "summarize my resume", "tell me about my resume", "about my background")
_NEXT_ACTION_KEYWORDS = ("what should i do next", "next step", "what now", "what should i do", "next best action")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


# The student (not a second job) is what is being compared: candidate <-> job fit.
_SELF_COMPARISON = re.compile(
    r"\bcompare\s+(me|myself|my\s+(profile|resume|cv|skills|background))\b"
    r"|\b(how|where)\s+(do|would|will)\s+i\s+(compare|stack\s+up|measure\s+up)\b"
    r"|\b(me|myself)\s+(vs\.?|versus|against)\b"
)
# Learning-priority wording ("which should I learn first", "what to prioritise"),
# matched on whole words so "machine learning" never counts as a learning request.
_LEARNING_VERB = re.compile(r"\b(learn|study|upskill|practice|practise|prioriti[sz]e|focus\s+on|work\s+on)\b")
_LEARNING_ORDER = re.compile(r"\b(first|next|priority|most\s+important|which|what|should\s+i)\b")
# General discovery wording ("find QA testing jobs", "suggest some cloud roles"),
# used only after every more specific rule has had its chance.
_DISCOVERY_VERB = re.compile(r"\b(find|search|look(ing)?\s+for|suggest|recommend|show|list|any)\b")
_OPPORTUNITY_NOUN = re.compile(r"\b(jobs?|internships?|roles?|opportunit(y|ies)|positions?|openings?|apprenticeships?|traineeships?|vacanc(y|ies))\b")


def classify_intent(message: str) -> tuple[str, float]:
    """Returns (intent, confidence). Pure text classification only — does not know
    about job ids, conversation history, or resume state; `detect_intent` layers
    that on top.
    """
    text = f" {message.strip().lower()} "

    if _SELF_COMPARISON.search(text) and len(extract_job_ids(message)) <= 1:
        return "JOB_MATCH_EXPLANATION", 0.85
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
    if _contains_any(text, _LEARNING_KEYWORDS) or (_LEARNING_VERB.search(text) and _LEARNING_ORDER.search(text)):
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
    if _DISCOVERY_VERB.search(text) and _OPPORTUNITY_NOUN.search(text):
        return "JOB_DISCOVERY", 0.7
    return "GENERAL_CAREER_CHAT", 0.5


_JOB_CONTEXT_INTENTS = {
    "JOB_MATCH_EXPLANATION", "SKILL_GAP", "RESUME_CUSTOMIZATION",
    "COVER_LETTER", "INTERVIEW_PREP", "LEARNING_GUIDANCE",
}
_RESUME_CONTEXT_INTENTS = {
    "JOB_MATCH_EXPLANATION", "SKILL_GAP", "RESUME_CUSTOMIZATION", "COVER_LETTER",
    "INTERVIEW_PREP", "LEARNING_GUIDANCE", "PROFILE_SUMMARY", "JOB_DISCOVERY",
}


def extract_discovery_request(message: str) -> str | None:
    """The area/role words of a job-discovery request, or None when the student only
    asked generically ("which internships fit my resume?"). Opportunity-type words are
    kept alongside area words ("cybersecurity internships") but never form a request
    on their own, so a generic request keeps the resume-driven discovery."""
    words = [word.strip("./-") for word in _WORD_PATTERN.findall(message.lower())]
    kept = [word for word in words if word and word not in _DISCOVERY_FILLER and not _JOB_ID_PATTERN.fullmatch(word)]
    if not any(word not in _OPPORTUNITY_TYPE_WORDS for word in kept):
        return None
    return " ".join(kept)


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
