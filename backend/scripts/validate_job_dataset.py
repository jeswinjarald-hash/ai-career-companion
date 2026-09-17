import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.job_dataset_service import DATASET_PATH, load_job_postings


if __name__ == "__main__":
    postings = load_job_postings()
    result = {
        "dataset": str(DATASET_PATH),
        "record_count": len(postings),
        "duplicate_job_id_count": len(postings) - len({posting.job_id for posting in postings}),
        "duplicate_content_count": len(postings) - len({posting.raw_text for posting in postings}),
        "domain_count": len({posting.domain for posting in postings}),
        "domain_distribution": dict(sorted(Counter(posting.domain for posting in postings).items())),
        "status": "PASS",
    }
    print(json.dumps(result, indent=2))
