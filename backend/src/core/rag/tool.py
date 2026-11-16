"""Callable Agent Tool: search_knowledge_base."""
import asyncio
import logging
from typing import Dict, Any, List
from src.core.rag.hybrid import search_dense_vectors, search_bm25_lexical
from src.core.rag.fusion import reciprocal_rank_fusion
from src.core.rag.reranker import reranker
from src.core.rag.embeddings import get_embedding
from src.core.db.session import db_manager
from src.config import settings

logger = logging.getLogger(__name__)

async def resolve_application_name(application_id: int) -> str:
    """Resolve application ID to its canonical name."""
    async with db_manager.acquire() as conn:
        row = await conn.fetchrow("SELECT name FROM applications WHERE id = $1", application_id)
        if row:
            return row["name"]
    return "General Knowledge"

async def search_knowledge_base(
    query: str,
    application_id: int = 1,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Search company knowledge base using hybrid dense/BM25 retrieval, RRF, and CrossEncoder reranking.
    """
    app_name = await resolve_application_name(application_id)
    logger.info(f"Executing knowledge_base_search: query='{query}', app='{app_name}'")

    # 1. Concurrent hybrid retrieval and approved overrides check
    dense_task = search_dense_vectors(query, app_name, limit=settings.RERANK_INITIAL_LIMIT)
    bm25_task = search_bm25_lexical(query, app_name, limit=settings.RERANK_INITIAL_LIMIT)
    dense_results, bm25_results = await asyncio.gather(dense_task, bm25_task)

    # 1.5 Check Approved Answers (Override Collection)
    async with db_manager.acquire() as conn:
        query_vec = await get_embedding(query)
        v_str = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"
        approved_row = await conn.fetchrow("""
            SELECT question_text, approved_answer, 1 - (dense_vector <=> $1::vector) as sim
            FROM approved_answers
            WHERE application_id = $2 AND status = 'answer_embedded'
            ORDER BY dense_vector <=> $1::vector ASC
            LIMIT 1;
        """, v_str, application_id)
        if approved_row and float(approved_row["sim"]) >= 0.85:
            logger.info(f"High-confidence verified answer override matched ({approved_row['sim']:.3f})")
            return {
                "status": "success",
                "count": 1,
                "passages": f"[Verified Company Answer]\n{approved_row['approved_answer']}",
                "citations": [{
                    "document_name": "Official Approved Q&A",
                    "section_title": approved_row["question_text"],
                    "snippet": approved_row["approved_answer"][:250],
                    "confidence_score": 0.99,
                    "chunk_id": "verified_override"
                }]
            }

    # 2. Reciprocal Rank Fusion
    fused_candidates = reciprocal_rank_fusion([dense_results, bm25_results], k=settings.RRF_K)

    # 3. CrossEncoder Reranking
    final_passages = reranker.rerank(query, fused_candidates, top_k=top_k)

    # 4. Format structured output for LLM consumption
    citations = []
    passages_text = []

    for idx, p in enumerate(final_passages, start=1):
        # Calculate human-intuitive confidence score (preferring dense cosine similarity 0.0-1.0)
        raw_sim = p.get("score")
        if raw_sim is not None and 0.1 <= float(raw_sim) <= 1.0:
            conf = round(float(raw_sim), 2)
        elif p.get("rerank_score") is not None:
            conf = round(float(p["rerank_score"]), 2)
        else:
            # Calibrate raw RRF rank score (typically 0.016 - 0.033) into a 0.65 - 0.95 confidence range
            conf = round(min(0.95, max(0.65, float(p.get("fused_score", 0.02)) * 26.0)), 2)

        citations.append({
            "document_name": p["filename"],
            "section_title": p.get("section_title"),
            "snippet": p["chunk_text"][:250] + "...",
            "confidence_score": conf,
            "chunk_id": p["chunk_id"]
        })
        passages_text.append(
            f"[{idx}] Source: {p['filename']} (Section: {p.get('section_title', 'General')})\n{p['chunk_text']}"
        )

    context_str = "\n\n---\n\n".join(passages_text) if passages_text else "No matching documents found in knowledge base."

    return {
        "status": "success",
        "count": len(final_passages),
        "passages": context_str,
        "citations": citations
    }

# Tool schema definition for LLM function calling
KNOWLEDGE_TOOL_SCHEMA = {
    "name": "knowledge_base_search",
    "description": "Searches the internal corporate knowledge base, company policies, manuals, and documentation.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The specific semantic search query or keywords to look up."
        },
        "application_id": {
          "type": "integer",
          "description": "The ID of the application knowledge base domain (default: 1)."
        }
      },
      "required": ["query"]
    }
}
