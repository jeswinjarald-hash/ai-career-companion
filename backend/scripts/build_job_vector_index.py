import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.services.embedding_service import embed_documents, embedding_dimension
from app.services.job_chunking import chunk_job_postings
from app.services.job_dataset_service import load_job_postings
from app.services.job_vector_store import INDEX_PATH, METADATA_PATH, build_index, save_vector_store


if __name__ == "__main__":
    jobs = load_job_postings()
    chunks = chunk_job_postings(jobs)
    embeddings = embed_documents([chunk.text for chunk in chunks])
    index = build_index(embeddings)
    save_vector_store(index, chunks)
    print(f"Jobs loaded: {len(jobs)}")
    print(f"Chunks generated: {len(chunks)}")
    print(f"Embedding model: {get_settings().embedding_model_name}")
    print(f"Embedding dimension: {embedding_dimension()}")
    print(f"Vectors indexed: {index.ntotal}")
    print(f"Index saved: {INDEX_PATH}")
    print(f"Metadata saved: {METADATA_PATH}")
    print("Status: PASS")
