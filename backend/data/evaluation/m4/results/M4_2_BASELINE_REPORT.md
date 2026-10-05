# Milestone 4.2 Baseline Evaluation Report

Generated 2026-10-05T07:15:21+00:00 by `scripts/run_m4_evaluation.py` (LLM mode: null provider (deterministic pipeline only)). All values are measured; nothing below has been tuned. Historical M2.4 results remain in `data/evaluation/results/`.

## Configuration

- Dataset: `backend/data/internships/career_opportunities_320.json` — 320 postings
- Index: IndexFlatIP (inner product on L2-normalised embeddings (cosine)), 960 vectors / 960 chunks, `data/vector_store/internship_jobs.faiss`
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dims)
- Retrieval: all chunks searched; per-job score = best chunk + 0.05 x sum(other chunks); no threshold
- Cases: {"positive_queries": 26, "relevant_job_labels": 136, "acceptable_job_labels": 612, "negative_queries": 12, "candidates": 5, "candidate_job_pairs": 8, "matching_scenarios": 4, "conversations": 7, "conversation_turns": 16, "job_discovery_probes": 3}

## Positive retrieval (job-level labels)

| Metric | @1 | @3 | @5 | @10 |
|---|---:|---:|---:|---:|
| hit | 0.885 | 1.000 | 1.000 | 1.000 |
| precision | 0.885 | 0.833 | 0.654 | 0.396 |
| relaxed_precision | 1.000 | 0.987 | 0.969 | 0.908 |
| recall | 0.314 | 0.738 | 0.874 | 0.926 |
| capped_recall | 0.885 | 0.987 | 0.983 | 0.978 |
| ndcg | 0.923 | 0.968 | 0.961 | 0.938 |

- MRR@10: 0.942; top-1 domain accuracy: 1.000
- Top-1 similarity scores of labelled queries: min 0.5119, median 0.7751, max 0.9023
- Search latency (warm): median 32.1 ms, max 375.8 ms

Weak cases (no relevant job at rank 1 or none in top 5):

- RP12 "junior data science developer": first relevant rank 2, top-5 grades [1, 2, 2, 2, 1], top-1 domain Data Science
- RP16 "database engineering trainee": first relevant rank 2, top-5 grades [1, 2, 1, 1, 1], top-1 domain Database / SQL
- RP25 "business analyst entry level": first relevant rank 2, top-5 grades [1, 2, 1, 1, 0], top-1 domain Data Analytics

## Negative / off-topic retrieval

| Query | Category | Top score | Shown as | Top result |
|---|---|---:|---:|---|
| chef pastry baking | unrelated | 0.1889 | 19% | JOB-0320 Mobile Apprentice (Mobile Development) |
| truck driver heavy vehicle licence | unrelated | 0.2509 | 25% | JOB-0058 Full Stack Developer Intern (Full Stack Development) |
| registered nurse hospital ward shifts | unrelated | 0.1714 | 17% | JOB-0304 Database Engineering Trainee (Database / SQL) |
| civil engineering site supervisor concrete | unrelated | 0.4003 | 40% | JOB-0285 Graduate Full Stack Engineer (Full Stack Development) |
| real estate sales agent commission | unrelated | 0.2714 | 27% | JOB-0224 Junior NLP Developer (Generative AI / NLP) |
| chartered accountant tax audit | unrelated | 0.2352 | 24% | JOB-0227 Junior QA Developer (Software Testing / QA) |
| plumbing and electrician apprenticeship | unrelated | 0.5115 | 51% | JOB-0315 Full Stack Apprentice (Full Stack Development) |
| zzzz qqqq | nonsense | 0.2766 | 28% | JOB-0154 Database Intern (Database / SQL) |
| asdf lorem ipsum 12345 | nonsense | 0.3213 | 32% | JOB-0264 Graduate NLP Engineer (Generative AI / NLP) |
| UI UX design internship with Figma | out_of_coverage | 0.6031 | 60% | JOB-0039 UI Engineering Intern (Frontend Development) |
| digital marketing SEO intern | out_of_coverage | 0.5495 | 55% | JOB-0056 Web Application Intern (Full Stack Development) |
| mechanical engineering CAD internship | out_of_coverage | 0.5868 | 59% | JOB-0005 Software Engineering Intern (Software Development) |

- Every query returned results: True. Highest unrelated/nonsense score 0.5115 vs lowest genuine top-1 0.5119 (ranges overlap: False, gap 0.0004).
- Out-of-coverage queries reach 0.6031; 2 of 26 genuine queries have a best score below the best off-topic score, so no single similarity threshold separates them.

## Matching

Per-job scenarios against JOB-0035 (weights {'required_skills': 0.35, 'preferred_skills': 0.15, 'experience': 0.15, 'education': 0.1, 'project_relevance': 0.15, 'qualifications': 0.1}):

| Scenario | Match score | Required | Preferred | Matched required | Semantic retrieval finds target domain |
|---|---:|---:|---:|---|---|
| A_required_strong | 54.8 | 0.75 | 0.00 | Python, SQL, Git | True |
| B_preferred_strong | 52.0 | 0.25 | 1.00 | Git | True |
| C_semantic_not_exact | 21.1 | 0.00 | 0.00 | - | True |
| D_unsuitable | 21.1 | 0.00 | 0.00 | - | False |

- HOLDS: A_required_strong scores above B_preferred_strong ([54.8, 52.0])
- HOLDS: D_unsuitable scores lowest and below 40 ([21.1])
- DOES NOT HOLD: C_semantic_not_exact scores above D_unsuitable ([21.1, 21.1])

M2.4 profiles re-run on the 320-record dataset: top-1 domain accuracy 1.000, top-3 hit 1.000, MRR 1.000 (7 labelled profiles).

## Matching <-> Skill Gap consistency

Pairs checked: 8; findings by type: {'education_disagreement': 2}; high severity: 0.

- [medium] GA x JOB-0121: Matching education score 0.0 vs skill-gap education score 0.5.
- [medium] PO x JOB-0121: Matching education score 0.0 vs skill-gap education score 0.5.

## Grounding

Pairs: 8; structured checks run: 921; violations by service: {'matching': 0, 'skill_gap': 0, 'customization': 0, 'cover_letter': 0, 'interview_prep': 0}.

- No violations.

Needs human review (heuristic flags, not counted as violations):

- customization/validator_removed_claims (GA x JOB-0035): 1 generated sentence(s) removed by the existing validator, e.g. "I am writing to express my interest in the FastAPI Intern position at QuantumLeaf Technologies. I was drawn to this oppo" — reasons: ['Removed from cover letter: "I am writing to express my interest in the FastAPI Intern position at QuantumLeaf Technologies. I was drawn to this opportunity in Python Backend, and I am excited about the possibility of contributing my skills and project experience to your team." (references unsupported keyword "fastapi").']
- matching,skill_gap,customization/profile_only_skill_treated_as_demonstrated (PO x JOB-0121): 'kubernetes' appears only in the career profile (no resume evidence) but is presented as demonstrated by: matching, skill_gap, customization
- matching,skill_gap,customization/profile_only_skill_treated_as_demonstrated (PO x JOB-0121): 'linux' appears only in the career profile (no resume evidence) but is presented as demonstrated by: matching, skill_gap, customization
- matching,skill_gap,customization/profile_only_skill_treated_as_demonstrated (PO x JOB-0121): 'docker' appears only in the career profile (no resume evidence) but is presented as demonstrated by: matching, skill_gap, customization

## Service handoff chain

SB x JOB-0035: all checks hold = True

- OK context_belongs_to_resume
- OK matches_reference_canonical_jobs
- OK target_job_retrieved_in_top10
- OK skill_gap_same_job
- OK skill_gap_same_resume
- OK customization_same_job
- OK customization_same_resume
- OK cover_letter_present_in_same_customization
- OK interview_prep_same_job
- OK interview_prep_same_resume
- OK candidate_evidence_unchanged
- OK matched_skills_agree_with_customization_supported_keywords

## Conversation

Turns passing desired behaviour: 12/16; conversations fully passing: 5/7.

- CV01_context_retention_compare_phrasing: FAIL
  - "Compare me with JOB-0035." -> intent JOB_COMPARISON, job JOB-0035; failed ['not_asking_for_context']; reply: "To compare two opportunities, please mention both ids (e.g. "compare JOB-0035 and JOB-0041")."
  - "What skills am I missing?" -> intent SKILL_GAP, job None; failed ['job_id', 'not_asking_for_context']; reply: "Which opportunity would you like me to use? You can mention its id (e.g. JOB-0035) or open its details page first."
  - "Which of those should I learn first?" -> intent GENERAL_CAREER_CHAT, job None; failed ['intent', 'job_id']; reply: "I can help with job recommendations, skill gaps, resume customization, cover letters, and interview preparation. Try ask"
- CV02_context_retention_supported_phrasing: PASS
- CV03_job_switch: PASS
- CV04_short_follow_up: PASS
- CV05_profile_awareness: PASS
- CV06_general_question: FAIL
  - "How should I negotiate a salary offer for my first job?" -> intent GENERAL_CAREER_CHAT, job None; failed ['substantive_answer']; reply: "I can help with job recommendations, skill gaps, resume customization, cover letters, and interview preparation. Try ask"
- CV07_explicit_comparison: PASS

Job discovery: identical results for different queries = True; expected-domain hit rate 0.000.

- "Find internships in cybersecurity." -> ['FastAPI Intern', 'Backend Developer Intern', 'FastAPI Intern', 'Python Developer Intern', 'FastAPI Intern']
- "Find internships in frontend React development." -> ['FastAPI Intern', 'Backend Developer Intern', 'FastAPI Intern', 'Python Developer Intern', 'FastAPI Intern']
- "Find internships for data analysts." -> ['FastAPI Intern', 'Backend Developer Intern', 'FastAPI Intern', 'Python Developer Intern', 'FastAPI Intern']

## Metric definitions

- **hit@k**: 1 if any grade-2 (relevant) job is in the top k, averaged over queries.
- **precision@k**: grade-2 jobs in the top k divided by k.
- **relaxed_precision@k**: grade-1 or grade-2 jobs in the top k divided by k.
- **recall@k**: grade-2 jobs in the top k divided by all grade-2 jobs for the query (bounded by k / label count).
- **capped_recall@k**: grade-2 jobs in the top k divided by min(label count, k).
- **mrr@10**: mean of 1 / rank of the first grade-2 job within the top 10 (0 if none).
- **ndcg@k**: graded nDCG with gains 3 (relevant) and 1 (acceptable); ideal ranking built from the labels.
- **top1_domain_accuracy**: top-ranked job's domain equals the query's expected domain.
- **negative: above_weakest_positive_top1**: an off-topic query's top score is at least the lowest top-1 score of any genuine labelled query, i.e. no single threshold could separate them.

Evaluation runtime: 5.4 s.
