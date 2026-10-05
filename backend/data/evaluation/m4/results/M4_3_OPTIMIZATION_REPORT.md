# Milestone 4.3 Optimization Report

Controlled optimization against the frozen M4.2 baseline (`m4_2_baseline_results.json`,
unchanged). Each logical change was measured on its own with the same evaluation
(`scripts/run_m4_evaluation.py`, null LLM, offline) before the next one; rejected
variants were reverted. Full per-experiment records: `m4_3_experiments.json`. Final
evaluation: `m4_3_optimized_results.json` / `M4_3_OPTIMIZED_EVALUATION.md`.

## Decisions

| ID | Change | Decision |
|---|---|---|
| E1 | Assistant discovery retrieves the requested area (resume still scores) | ACCEPT |
| E2a | Routing: "compare me with JOB-X" = fit; learning-priority follow-ups; free-form discovery wording | ACCEPT |
| E2b | Substantive answers to general career questions | REJECT (deferred: needs LLM, unmeasurable here) |
| E3a | Bidirectional related skills, partial credit for required + preferred | REJECT (B overtook A) |
| E3b | E3a + preferred credit gated by required coverage | REJECT (P001, P005 score regressions) |
| E3c | E3b + required 0.45 / preferred 0.10 | REJECT (A-B 7.3, P005 regression) |
| E3e | Shared bidirectional related skills, partial credit for preferred only (+ node.js normalisation fix) | ACCEPT |
| E4 | One education assessment shared by matching and skill gap | ACCEPT |
| E5 | Naming the target role/company is not a skill claim (final + LLM-layer validator, evaluator) | ACCEPT |
| E6 | Query-coverage confidence flag (C); absolute threshold (A), margin (B), hybrid (E) | ACCEPT C as a flag; A, B, E REJECT |
| E7 | Profile-only skills described as self-reported | ACCEPT |
| E8 | Title/type in index text: V1 extra chunk, V2 every chunk, V3 overview only | V1 REJECT, V2 REJECT (integration regression), V3 ACCEPT |
| E9 | Local-first embedding model loading | ACCEPT |
| E10 | Keyed in-process caches for dataset and vector store | ACCEPT |
| T1 | Capture provider-reported token usage | ACCEPT (instrumentation) |
| P1 | Prompt review | No prompt change |

## Before -> after (frozen M4.2 baseline -> final)

| Metric | Baseline | Final |
|---|---:|---:|
| Retrieval Hit@1 / Hit@3 / Hit@5 | 0.885 / 1.000 / 1.000 | **1.000** / 1.000 / 1.000 |
| Precision@1 / Precision@5 | 0.885 / 0.654 | **1.000 / 0.662** |
| Recall@5 / Recall@10 | 0.874 / 0.926 | **0.883 / 0.936** |
| MRR@10 | 0.942 | **1.000** |
| nDCG@5 / nDCG@10 | 0.961 / 0.938 | **0.969** / 0.938 |
| Off-topic queries suppressed or flagged | 0/12 | **11/12** (miss: "UI UX design internship with Figma") |
| Genuine queries flagged | 0/26 | 0/26 |
| Matching A / B / C / D | 54.8 / 52.0 / 21.1 / 21.1 | 56.5 / 52.0 / **26.1** / 21.1 |
| M2 profile top-1 domain accuracy | 1.0 | 1.0 |
| Matching <-> skill-gap findings | 2 (education) | **0** |
| Grounding violations / review items | 0 / 4 | 0 / **0** |
| Fault injections detected | 9/9 | **10/10** |
| Conversation turns | 12/16 | **15/16** |
| Discovery: requested area retrieved | 0/3 | **3/3** |
| Handoff chain | all hold | all hold |
| Evaluation runtime | 5.5 s | 2.2 s |

Targets not met (reported, not tuned further): A-B >= 10 (4.5) and C-D >= 10 (5.0);
CV06 general question (needs the LLM path); RO01 not flagged (its words "UI" and
"design" exist in the catalogue). Held-out check of the confidence rule: 10/10 off-topic
flagged, 1/10 genuine flagged ("Linux system administration trainee").

## Performance (median of repeated warm calls, same machine)

| Stage | Before | After |
|---|---:|---:|
| Dataset load + validation | 17.87 ms | 0.24 ms |
| Vector store load | 4.94 ms | 0.14 ms |
| Query embedding | 7.67 ms | 5.27 ms |
| FAISS search (960 vectors) | 0.39 ms | 0.09 ms |
| `search_jobs` total | 46.71 ms | 9.44 ms |
| `match_jobs_for_resume` (top 10) | 78.05 ms | 16.31 ms |
| Skill gap | 27.61 ms | 3.07 ms |
| Customization (deterministic) | 20.04 ms | 4.57 ms |
| Cold model load, network allowed | 12.1-12.3 s | 7.3 s |
| Full backend suite without HF_HUB_OFFLINE | hung > 20 min (M4.2A) | 30.5 s |

Embedding and FAISS were not changed; their small differences are run-to-run variation.
Token usage is not measured in the automated baseline because live LLM execution is
intentionally disabled; the provider now records reported usage when a live model is used.

## Canonical artifacts

- Dataset `career_opportunities_320.json`: unchanged (sha1 d9401f90...), validates 320 records.
- FAISS index rebuilt once for the accepted E8-V3 template: 960 vectors, index version 1.2.
  V2 (v1.1) was built, found to regress, and replaced.
