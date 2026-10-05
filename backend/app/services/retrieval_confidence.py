"""Query-coverage confidence for opportunity search (M4.3 Experiment 6).

Similarity scores alone cannot tell an off-topic search from a genuine one: in the M4.2
baseline an "electrician apprenticeship" query (0.51) and out-of-coverage queries such
as "UI UX design" (0.60) scored above genuine skill-only queries (0.51-0.58), so no single
threshold separates them. Instead, this measures how much of the query's content
vocabulary exists anywhere in the opportunity catalogue (job titles, domains, required
and preferred skills). Results are never suppressed — a low-coverage query is only
labelled `unsupported_area` so the UI and assistant can say the matches may not fit.

The vocabulary is derived from the loaded dataset at runtime (no hard-coded domains) and
cached for the process; `opportunity_vocabulary.cache_clear()` resets it.
"""

import re
from functools import lru_cache
from typing import Literal

QueryConfidence = Literal["confident", "unsupported_area"]

# Below this share of recognised content words a query is labelled unsupported_area.
MIN_TERM_COVERAGE = 0.5

# Grammar words and generic opportunity nouns carry no subject area, on either side.
_STOPWORDS = frozenset(
    "a an the and or of in on for with to at by from as is are be my me i we you our your this that it its "
    "role roles job jobs position positions opportunity opportunities program programme programs work career".split()
)
_OPPORTUNITY_WORDS = frozenset(
    "internship internships intern interns entry level graduate trainee apprenticeship apprentice apprenticeships junior".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9+#./-]*")


def _words(text: str) -> list[str]:
    return [word.strip("./-") for word in _WORD.findall(text.lower()) if word.strip("./-")]


@lru_cache(maxsize=1)
def opportunity_vocabulary() -> frozenset[str]:
    from app.services.job_dataset_service import load_job_postings

    vocabulary: set[str] = set()
    for job in load_job_postings():
        for text in (job.job_title, job.domain, *job.required_skills, *job.preferred_skills):
            vocabulary.update(_words(text))
    return frozenset(vocabulary - _STOPWORDS - _OPPORTUNITY_WORDS)


def query_term_coverage(query: str) -> float:
    terms = [word for word in _words(query) if word not in _STOPWORDS and word not in _OPPORTUNITY_WORDS]
    if not terms:
        return 0.0
    vocabulary = opportunity_vocabulary()
    # Plural-tolerant: "analysts" is recognised when "analyst" is in the catalogue.
    return sum(1 for term in terms if term in vocabulary or term.rstrip("s") in vocabulary) / len(terms)


def query_confidence(query: str) -> QueryConfidence:
    return "confident" if query_term_coverage(query) >= MIN_TERM_COVERAGE else "unsupported_area"
