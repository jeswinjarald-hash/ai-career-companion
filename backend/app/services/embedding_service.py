from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


class EmbeddingError(ValueError):
    pass


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(get_settings().embedding_model_name)


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
