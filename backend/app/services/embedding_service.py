import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(ValueError):
    pass


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Loads the embedding model from the local cache first, with no Hugging Face hub
    network checks (those added ~5 s per cold start on a healthy network and hung
    indefinitely when the hub was unreachable — M4.3 Experiment 9). Only a model that
    is not cached yet is downloaded, and only when `embedding_allow_download` is on."""
    settings = get_settings()
    name = settings.embedding_model_name
    try:
        return SentenceTransformer(name, local_files_only=True)
    except Exception as exc:  # the cache miss surfaces as different exception types across versions
        if not settings.embedding_allow_download:
            raise EmbeddingError(
                f"Embedding model '{name}' is not in the local cache and downloading is disabled "
                "(EMBEDDING_ALLOW_DOWNLOAD=false). Download it once with network access, or enable downloads."
            ) from exc
        logger.warning("embedding_model_not_cached model=%s — downloading (first install)", name)
        print(f"Embedding model '{name}' is not cached locally; downloading it (first install).", flush=True)
        return SentenceTransformer(name)


def _validate_texts(texts: list[str], name: str) -> None:
    if not texts:
        raise EmbeddingError(f"{name} must contain at least one text.")
    if any(not text.strip() for text in texts):
        raise EmbeddingError(f"{name} must not contain empty text.")


def embed_documents(texts: list[str]) -> np.ndarray:
    _validate_texts(texts, "texts")
    embeddings = get_embedding_model().encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(embeddings, dtype=np.float32)


def embed_query(query: str) -> np.ndarray:
    _validate_texts([query], "query")
    return embed_documents([query])[0]


def embedding_dimension() -> int:
    model = get_embedding_model()
    get_dimension = (
        model.get_embedding_dimension
        if hasattr(model, "get_embedding_dimension")
        else model.get_sentence_embedding_dimension
    )
    return int(get_dimension())
