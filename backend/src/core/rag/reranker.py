"""CrossEncoder Semantic Reranker Integration."""
import logging
from typing import List, Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

class SemanticReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading CrossEncoder model: {self.model_name}...")
                self._model = CrossEncoder(self.model_name)
                logger.info("CrossEncoder loaded successfully.")
            except Exception as e:
                logger.warning(f"Failed to load CrossEncoder ({e}). Reranking will use fused scores.")
                self._model = False
        return self._model

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Score candidate chunks against the query and retain top_k."""
        if not candidates:
            return []

        if not settings.RERANKING_ENABLED:
            return candidates[:top_k]

        model = self._get_model()
        if not model:
            # Fallback to fused rank ordering if CrossEncoder model unavailable
            return candidates[:top_k]

        try:
            pairs = [[query, doc["chunk_text"]] for doc in candidates]
            scores = model.predict(pairs)

            for doc, score in zip(candidates, scores):
                doc["rerank_score"] = float(score)

            # Sort by rerank score descending
            reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            return reranked[:top_k]
        except Exception as e:
            logger.error(f"CrossEncoder inference error: {e}")
            return candidates[:top_k]

reranker = SemanticReranker()
