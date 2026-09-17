# Milestone 2.4 Evaluation Report

## 1. Evaluation Setup

- Dataset size: 180
- Retrieval queries: 20
- Student profiles: 8
- Retrieval K values: 1, 3, 5
- Embedding model: sentence-transformers/all-MiniLM-L6-v2
- Matching weights: {'required_skills': 0.35, 'preferred_skills': 0.15, 'experience': 0.15, 'education': 0.1, 'project_relevance': 0.15, 'qualifications': 0.1}

## 2. Retrieval Evaluation

| Query | Expected Primary | Top-1 Domain | Precision@5 | Recall@5 | First Relevant Rank | Pass |
|---|---|---|---:|---:|---:|---|
| RQ001 | Machine Learning | Machine Learning | 1.000 | 0.333 | 1 | PASS |
| RQ002 | Frontend Development | Frontend Development | 1.000 | 0.500 | 1 | PASS |
| RQ003 | Java Backend | Java Backend | 1.000 | 0.500 | 1 | PASS |
| RQ004 | Python Backend | Python Backend | 1.000 | 0.500 | 1 | PASS |
| RQ005 | Full Stack Development | Frontend Development | 0.600 | 0.667 | 2 | PASS |
| RQ006 | Data Science | Data Science | 1.000 | 0.333 | 1 | PASS |
| RQ007 | Generative AI / NLP | Generative AI / NLP | 1.000 | 0.333 | 1 | PASS |
| RQ008 | Data Analytics | Data Analytics | 1.000 | 0.500 | 1 | PASS |
| RQ009 | Cloud Computing | Cloud Computing | 1.000 | 0.500 | 1 | PASS |
| RQ010 | DevOps | DevOps | 1.000 | 0.500 | 1 | PASS |
| RQ011 | Cybersecurity | Cybersecurity | 1.000 | 0.500 | 1 | PASS |
| RQ012 | Database / SQL | Database / SQL | 1.000 | 0.333 | 1 | PASS |
| RQ013 | Software Testing / QA | Software Testing / QA | 1.000 | 0.500 | 1 | PASS |
| RQ014 | Mobile Development | Mobile Development | 1.000 | 0.500 | 1 | PASS |
| RQ015 | Software Development | Python Backend | 0.400 | 1.000 | 4 | PASS |
| RQ016 | Generative AI / NLP | Generative AI / NLP | 1.000 | 0.333 | 1 | PASS |
| RQ017 | Data Analytics | Data Analytics | 1.000 | 0.333 | 1 | PASS |
| RQ018 | Cloud Computing, DevOps | DevOps | 1.000 | 1.000 | 1 | PASS |
| RQ019 | Mobile Development | Mobile Development | 0.800 | 1.000 | 1 | PASS |
| RQ020 | Python Backend | Python Backend | 1.000 | 0.333 | 1 | PASS |

| Metric | Value |
|---|---:|
| hit_rate_at_1 | 0.900 |
| hit_rate_at_3 | 0.950 |
| hit_rate_at_5 | 1.000 |
| strict_precision_at_5 | 0.940 |
| relaxed_precision_at_5 | 1.000 |
| domain_recall_at_5 | 0.525 |
| mrr | 0.938 |
| ndcg_at_5 | 0.745 |

## 3. Matching Evaluation

| Profile | Expected Primary | Top Domain | Top Score | Top-1 | Top-3 | Top-5 Relaxed |
|---|---|---|---:|---|---|---|
| P001 Machine Learning Student | Machine Learning, Data Science | Data Science | 60.0 | PASS | PASS | PASS |
| P002 Frontend Student | Frontend Development | Frontend Development | 71.5 | PASS | PASS | PASS |
| P003 Python Backend Student | Python Backend | Python Backend | 70.1 | PASS | PASS | PASS |
| P004 Java Backend Student | Java Backend | Java Backend | 71.5 | PASS | PASS | PASS |
| P005 Cybersecurity Student | Cybersecurity | Cybersecurity | 51.2 | PASS | PASS | PASS |
| P006 Data Analyst Student | Data Analytics | Data Analytics | 70.1 | PASS | PASS | PASS |
| P007 Cloud DevOps Student | Cloud Computing, DevOps | Cloud Computing | 54.2 | PASS | PASS | PASS |
| P008 Weak General Student | None | Full Stack Development | 36.5 | FAIL | FAIL | FAIL |

| Metric | Value |
|---|---:|
| top1_domain_accuracy | 0.875 |
| top3_hit_rate | 0.875 |
| top5_relaxed_hit_rate | 0.875 |
| mrr | 0.875 |

## 4. Skill Matching Accuracy

- Cases: 4
- Accuracy: 1.000
- Alias cases: 1
- Negative alias cases: 1

## 5. Score Consistency

- base_score: 60.7
- added_score: 60.7
- removed_score: 56.7
- unrelated_score: 60.7
- repeat_score: 60.7
- determinism: PASS
- addition_monotonic: PASS
- removal_monotonic: PASS
- unrelated_robust: PASS

## 6. Explanation Quality

- Explanations checked: 40
- Unsupported claims: 0
- Factuality pass rate: 1.000

## 7. Failures / Limitations

Independently authored expectation failures:
- P007 score behavior threshold
- Relevance is domain-level and uses synthetic postings.
- Education and experience checks are conservative rule-based heuristics.
- Retrieval results can mix adjacent technical domains.
- M2.4 does not tune M2.2 or M2.3 and does not implement external-market evaluation.

## 8. Conclusion

**M2.4 COMPLETE**
