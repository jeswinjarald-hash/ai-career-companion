# Milestone 4.2 Evaluation

Measurement framework for the complete AI Career Companion workflow. It records how the
current system behaves; it does not tune anything. Weak results are baseline evidence
for Milestone 4.3 (baseline → observed weakness → controlled change → re-evaluation).

Historical Milestone 2.4 artifacts (180-record dataset era) stay unchanged in
`../results/`. Everything for M4 lives here.

## Layout

| Path | Contents |
|---|---|
| `cases/retrieval_positive.json` | 26 labelled queries over the 320-record dataset (job-level grades) |
| `cases/retrieval_negative.json` | 12 off-topic queries: unrelated, nonsense, out-of-coverage |
| `cases/candidates.json` | 5 synthetic candidates + 4 required/preferred matching scenarios |
| `cases/conversations.json` | 7 multi-turn assistant scripts + a job-discovery probe |
| `results/m4_2_baseline_results.json` | Frozen M4.2 baseline (per-query, per-pair, per-turn) — never overwritten |
| `results/M4_2_BASELINE_REPORT.md` | Frozen human-readable M4.2 summary |
| `results/m4_3_experiments.json` | M4.3 experiment log: hypothesis, change, baseline, result, regressions, decision |
| `results/M4_3_OPTIMIZATION_REPORT.md` | M4.3 decisions and before/after summary |
| `results/m4_3_optimized_results.json`, `M4_3_OPTIMIZED_EVALUATION.md` | Latest runner output (overwritten on each run) |

Code: `app/services/m4_evaluation.py` (extends `m2_4_evaluation.py`, reusing its profile
matching evaluation and the M3.2 fabrication validator) and `scripts/run_m4_evaluation.py`.

## Running

```
cd backend
python scripts/run_m4_evaluation.py                  # writes results/m4_3_optimized_* and prints the diff vs the frozen M4.2 baseline
python scripts/run_m4_evaluation.py --output-dir X   # writes elsewhere
```

The runner is deterministic and offline: it forces `LLM_PROVIDER=none` before importing
the app and wraps the run in `m4_evaluation.null_llm()`, so a live key in `backend/.env`
is never used. It sets `HF_HUB_OFFLINE=1` so the cached embedding model loads without
network checks. Runtime is a few seconds. There is no live-LLM evaluation mode; the LLM
rewrite layer is covered by the existing fake-provider unit tests.

## Label policy (retrieval)

Every posting inside one domain shares identical required and preferred skills, so
job-level relevance can only be distinguished by job title and opportunity type. Each
positive case stores the explicit rule it was derived from (domain + exact titles and/or
employment types) next to the resulting job IDs:

- **relevant (grade 2)**: postings matching `relevant_rule`;
- **acceptable (grade 1)**: other postings matching `acceptable_rule` (same or adjacent domain);
- **everything else (grade 0)**.

`tests/test_m4_2_evaluation_framework.py` re-derives every label from its rule, so a
dataset change that silently invalidates the labels fails the suite. Skill-only queries
(RP20, RP21) label the whole domain relevant because no posting is more relevant than
another.

## What each section measures

| Section | Measures | Kind |
|---|---|---|
| Positive retrieval | HitRate / Precision / relaxed Precision / Recall / capped Recall / nDCG @1,3,5,10, MRR@10, top-1 domain accuracy | Relevance evaluation against labels |
| Negative retrieval | Result count, top score, the "% relevance" the Careers page would show, overlap with genuine queries | Measurement only (no threshold exists) |
| Matching scenarios | Per-job score for required-strong, preferred-strong, semantic-not-exact and unsuitable profiles against JOB-0035 | Behaviour record + desired-property checks |
| M2.4 profiles | The original 8 profiles re-run on the 320-record dataset (domain-level) | Relevance evaluation |
| Matching ↔ Skill Gap | For the same candidate and job: matched-vs-missing, missing-vs-demonstrated, high score with most required missing, score gap ≥ 25, education/experience disagreement | Heuristic contradiction detection |
| Grounding | Absent skills never matched, demonstrated, listed, classified as supported or claimed; evidence quotes exist in the candidate data; no invented projects, experience, education or certifications; cover-letter evidence IDs exist; missing required skills become gaps and interview topics; learning-only skills never become demonstrated | Structured correctness checks |
| Needs review | Profile-only skills presented as demonstrated, sentences the existing validator removed | Human review |
| Handoff chain | Resume → context → match → gap → customization → interview prep keep the same resume, job, title and company; candidate evidence is unchanged | Correctness |
| Conversation | Intent, job used per turn, whether the assistant had to ask for context, no leaking of a previous job, profile facts, no absent-skill claims | Desired-behaviour checks |
| Job discovery | Whether different requested areas change the jobs returned | Behaviour record |

The test suite turns these into three kinds of assertion (see `tests/test_m4_2_baseline.py`):
correctness invariants, regression floors just below the measured baseline, and strict
`xfail` tests that assert the desired behaviour for each known weakness. A strict xfail
that starts passing fails the suite, so the marker is removed once M4.3 fixes it.

## Limits

- Labels cover 26 queries and 15 domains. They are rule-based, not crowd-judged.
- Candidates are synthetic and few (5 candidates, 8 candidate–job pairs). Results describe
  these fixtures, not the population of real resumes.
- Grounding checks are structural. They do not judge prose quality, and they flag only
  the fabrication shapes the existing validator knows (unsupported keywords, metrics,
  leadership, years of experience).
- Everything runs with the deterministic pipeline. LLM-rewritten output is not evaluated here.
- Latency figures are single-machine, warm-cache measurements of the search call only.
