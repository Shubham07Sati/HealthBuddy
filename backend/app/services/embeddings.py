"""
Embedding Service
=================
Shared text -> vector embedding helper backing the vector store (Qdrant).

No other service in the codebase generates embeddings yet -- the vector
store service only *stores*/*searches* pre-built vectors -- so this module
is the single place that owns model loading and encoding. It intentionally
does not talk to Qdrant directly; that stays the responsibility of
`app.services.vector_store.VectorStoreService`.

Two sentence-transformer models are supported (see Settings):
  * `embedding_model_biomedical` -- domain-tuned model, used by default for
    clinical knowledge retrieval, since PubMedBERT-style models embed
    clinical terminology (lab names, drug names, guideline language)
    meaningfully closer together than a general-purpose model would.
  * `embedding_model_general` -- fallback / general text.

Model loading is lazy and cached per-model-name so importing this module
has no side effects and repeated calls don't reload the model from disk.
"""
import logging
from functools import lru_cache
from typing import List

from app.core.config import get_settings
from app.core.exceptions import KnowledgeRetrievalError

log = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=4)
def _load_model(model_name: str):
    """
    Load (and cache) a SentenceTransformer model by name.

    Import is deferred to call time rather than module load time: the
    sentence-transformers/torch stack is heavy to import, and plenty of
    code paths (e.g. unit tests for unrelated agents) never need it.
    """
    from sentence_transformers import SentenceTransformer

    log.info(f"Loading embedding model '{model_name}'")
    return SentenceTransformer(model_name)


class EmbeddingService:
    """Encodes text into vectors for storage/search against Qdrant collections."""

    def __init__(self) -> None:
        self.general_model_name = settings.embedding_model_general
        self.biomedical_model_name = settings.embedding_model_biomedical
        self.use_biomedical = settings.embedding_use_biomedical_model
        self.dimension = settings.embedding_dimension

    def _model_name(self, biomedical: bool) -> str:
        return self.biomedical_model_name if biomedical else self.general_model_name

    def embed_text(self, text: str, biomedical: bool = True) -> List[float]:
        """Encode a single string into an embedding vector."""
        vectors = self.embed_texts([text], biomedical=biomedical)
        return vectors[0]

    def embed_texts(self, texts: List[str], biomedical: bool = True) -> List[List[float]]:
        """
        Encode a batch of strings. Returns one vector per input string, in
        the same order.

        Raises KnowledgeRetrievalError (not a bare Exception) on failure so
        callers in the Knowledge Agent can distinguish "embedding backend
        unreachable/broken" from "no results found".
        """
        if not texts:
            return []

        model_name = self._model_name(biomedical)
        try:
            model = _load_model(model_name)
            embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return [vec.tolist() for vec in embeddings]
        except Exception as exc:
            log.exception(f"Embedding generation failed using model '{model_name}'")
            raise KnowledgeRetrievalError(
                message="Failed to generate query embeddings",
                detail=str(exc),
            ) from exc


embedding_service = EmbeddingService()
