# Milestone 4.3 Optimized Evaluation Report

Generated 2026-10-10T05:00:46+00:00 by `scripts/run_m4_evaluation.py` (LLM mode: null provider (deterministic pipeline only)). All values are measured by this run. Compare with the frozen M4.2 baseline (`results/m4_2_baseline_results.json`); accepted and rejected M4.3 changes are recorded in `results/m4_3_experiments.json`. Historical M2.4 results remain in `data/evaluation/results/`.

## Configuration

- Dataset: `backend/data/internships/career_opportunities_320.json` — 320 postings
- Index: IndexFlatIP (inner product on L2-normalised embeddings (cosine)), 960 vectors / 960 chunks, `data/vector_store/internship_jobs.faiss`
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dims)
- Retrieval: all chunks searched; per-job score = best chunk + 0.05 x sum(other chunks); no score threshold (results are never suppressed); each result carries a query-coverage confidence flag (M4.3 E6)
- Cases: {"positive_queries": 26, "relevant_job_labels": 136, "acceptable_job_labels": 612, "negative_queries": 12, "candidates": 5, "candidate_job_pairs": 8, "matching_scenarios": 4, "conversations": 7, "conversation_turns": 16, "job_discovery_probes": 3}

## Positive retrieval (job-level labels)

| Metric | @1 | @3 | @5 | @10 |
|---|---:|---:|---:|---:|
| hit | 1.000 | 1.000 | 1.000 | 1.000 |
| precision | 1.000 | 0.846 | 0.661 | 0.404 |
| relaxed_precision | 1.000 | 0.962 | 0.939 | 0.881 |
| recall | 0.404 | 0.751 | 0.883 | 0.936 |
| capped_recall | 1.000 | 1.000 | 0.992 | 0.989 |
| ndcg | 1.000 | 0.984 | 0.969 | 0.938 |

- MRR@10: 1.000; top-1 domain accuracy: 1.000
- Top-1 similarity scores of labelled queries: min 0.4877, median 0.8367, max 0.9237
- Search latency (warm): median 17.2 ms, max 466.0 ms

Weak cases (no relevant job at rank 1 or none in top 5):


## Negative / off-topic retrieval

| Query | Category | Top score | Shown as | Top result |
|---|---|---:|---:|---|
| chef pastry baking | unrelated | 0.1879 | 19% | JOB-0273 Graduate DevOps Engineer (DevOps) |
| truck driver heavy vehicle licence | unrelated | 0.2484 | 25% | JOB-0058 Full Stack Developer Intern (Full Stack Development) |
| registered nurse hospital ward shifts | unrelated | 0.1578 | 16% | JOB-0304 Database Engineering Trainee (Database / SQL) |
| civil engineering site supervisor concrete | unrelated | 0.3936 | 39% | JOB-0285 Graduate Full Stack Engineer (Full Stack Development) |
| real estate sales agent commission | unrelated | 0.2678 | 27% | JOB-0224 Junior NLP Developer (Generative AI / NLP) |
| chartered accountant tax audit | unrelated | 0.238 | 24% | JOB-0227 Junior QA Developer (Software Testing / QA) |
| plumbing and electrician apprenticeship | unrelated | 0.5448 | 54% | JOB-0317 Data Analytics Apprentice (Data Analytics) |
| zzzz qqqq | nonsense | 0.2748 | 27% | JOB-0154 Database Intern (Database / SQL) |
| asdf lorem ipsum 12345 | nonsense | 0.2985 | 30% | JOB-0264 Graduate NLP Engineer (Generative AI / NLP) |
| UI UX design internship with Figma | out_of_coverage | 0.6365 | 64% | JOB-0045 UI Engineering Intern (Frontend Development) |
| digital marketing SEO intern | out_of_coverage | 0.5759 | 58% | JOB-0056 Web Application Intern (Full Stack Development) |
| mechanical engineering CAD internship | out_of_coverage | 0.651 | 65% | JOB-0005 Software Engineering Intern (Software Development) |

- Every query returned results: True. Highest unrelated/nonsense score 0.5448 vs lowest genuine top-1 0.4877 (ranges overlap: True, gap -0.0571).
- Out-of-coverage queries reach 0.651; 2 of 26 genuine queries have a best score below the best off-topic score, so no single similarity threshold separates them.
- Query-confidence flag (results are labelled, never removed): 11/12 off-topic queries flagged (not flagged: RO01); 0/26 genuine queries flagged.

## Matching

Per-job scenarios against JOB-0035 (weights {'required_skills': 0.35, 'preferred_skills': 0.15, 'experience': 0.15, 'education': 0.1, 'project_relevance': 0.15, 'qualifications': 0.1}):

| Scenario | Match score | Required | Preferred | Matched required | Semantic retrieval finds target domain |
|---|---:|---:|---:|---|---|
| A_required_strong | 56.5 | 0.75 | 0.10 | Python, SQL, Git | True |
| B_preferred_strong | 52.0 | 0.25 | 1.00 | Git | True |
| C_semantic_not_exact | 26.1 | 0.00 | 0.30 | - | True |
| D_unsuitable | 21.1 | 0.00 | 0.00 | - | False |

- HOLDS: A_required_strong scores above B_preferred_strong ([56.5, 52.0])
- HOLDS: D_unsuitable scores lowest and below 40 ([21.1])
- HOLDS: C_semantic_not_exact scores above D_unsuitable ([26.1, 21.1])

M2.4 profiles re-run on the 320-record dataset: top-1 domain accuracy 1.000, top-3 hit 1.000, MRR 1.000 (7 labelled profiles).

## Matching <-> Skill Gap consistency

Pairs checked: 8; findings by type: {}; high severity: 0.


## Grounding

Pairs: 8; structured checks run: 926; violations by service: {'matching': 0, 'skill_gap': 0, 'customization': 0, 'cover_letter': 0, 'interview_prep': 0}.

- No violations.

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

Turns passing desired behaviour: 15/16; conversations fully passing: 6/7.

- CV01_context_retention_compare_phrasing: PASS
- CV02_context_retention_supported_phrasing: PASS
- CV03_job_switch: PASS
- CV04_short_follow_up: PASS
- CV05_profile_awareness: PASS
- CV06_general_question: FAIL
  - "How should I negotiate a salary offer for my first job?" -> intent GENERAL_CAREER_CHAT, job None; failed ['substantive_answer']; reply: "I can help with job recommendations, skill gaps, resume customization, cover letters, and interview preparation. Try ask"
- CV07_explicit_comparison: PASS

Job discovery: identical results for different queries = False; expected-domain hit rate 1.000.

- "Find internships in cybersecurity." -> ['Cybersecurity Intern', 'Cybersecurity Intern', 'Cybersecurity Intern', 'Security Analyst Intern', 'Cybersecurity Intern']
- "Find internships in frontend React development." -> ['React Developer Intern', 'React Developer Intern', 'React Developer Intern', 'Frontend Developer Intern', 'React Developer Intern']
- "Find internships for data analysts." -> ['Data Analyst Intern', 'Data Analyst Intern', 'Data Analyst Intern', 'Data Analyst Intern', 'Business Data Analyst Intern']

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

Evaluation runtime: 3.2 s.
