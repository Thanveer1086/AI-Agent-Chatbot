"""Reciprocal Rank Fusion (RRF) algorithm for combining multiple retrieval channels."""
from typing import List, Dict, Any
from src.config import settings

def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Combines multiple ranked candidate lists into a single fused ranking.
    Formula: RRF_Score(d) = sum(1 / (k + rank_i(d)))
    """
    scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        for rank, doc in enumerate(ranked_list, start=1):
            doc_id = doc["chunk_id"]
            if doc_id not in scores:
                scores[doc_id] = 0.0
                doc_map[doc_id] = dict(doc)
            elif doc.get("retrieval_type") == "dense":
                # Ensure dense vector similarity score is retained
                doc_map[doc_id]["score"] = doc["score"]
                doc_map[doc_id]["retrieval_type"] = "dense"

            scores[doc_id] += 1.0 / (k + rank)

    # Sort documents by fused score descending
    sorted_doc_ids = sorted(scores.keys(), key=lambda doc_id: scores[doc_id], reverse=True)

    fused_results = []
    for doc_id in sorted_doc_ids:
        item = dict(doc_map[doc_id])
        item["fused_score"] = scores[doc_id]
        fused_results.append(item)

    return fused_results
