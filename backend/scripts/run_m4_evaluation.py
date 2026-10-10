"""Milestone 4 evaluation runner.

    python scripts/run_m4_evaluation.py                 # writes data/evaluation/m4/results/m4_3_optimized_*
    python scripts/run_m4_evaluation.py --output-dir X  # writes somewhere else (e.g. a scratch run)

Every run is compared against the frozen M4.2 baseline
(results/m4_2_baseline_results.json), which this script never overwrites.

Deterministic and offline: the LLM provider is forced to "none" before any app
module is imported (and `m4_evaluation.null_llm()` patches every provider binding as
a second guard), so a live key in backend/.env is never used and no API quota is
spent. The Hugging Face hub is put in offline mode so the already-cached embedding
model loads without network checks. Historical M2.4 results under
data/evaluation/results/ are never touched.
"""

import argparse
import json
import os
import sys
from pathlib import Path

os.environ["LLM_PROVIDER"] = "none"
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.m4_evaluation import (  # noqa: E402
    FROZEN_BASELINE_NAMES, RESULTS_DIR, compare_with_baseline, key_metrics, render_markdown, run_m4_evaluation,
)

JSON_NAME = "m4_3_optimized_results.json"
MARKDOWN_NAME = "M4_3_OPTIMIZED_EVALUATION.md"
REPORT_TITLE = "Milestone 4.3 Optimized Evaluation Report"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    report = run_m4_evaluation()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in (JSON_NAME, MARKDOWN_NAME):
        if name in FROZEN_BASELINE_NAMES:
            raise SystemExit(f"Refusing to overwrite frozen baseline file {name}.")
    (args.output_dir / JSON_NAME).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (args.output_dir / MARKDOWN_NAME).write_text(render_markdown(report, REPORT_TITLE), encoding="utf-8")

    baseline = json.loads((RESULTS_DIR / "m4_2_baseline_results.json").read_text(encoding="utf-8"))
    print(json.dumps({"results": str(args.output_dir), "current": key_metrics(report),
                      "changed_vs_frozen_m4_2_baseline": compare_with_baseline(baseline, report)}, indent=2))


if __name__ == "__main__":
    main()
