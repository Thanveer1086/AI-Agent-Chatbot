"""RAG building blocks: lexical query builder, chunking, parsing, fusion."""
from pathlib import Path

import pytest

from src.core.rag.fusion import reciprocal_rank_fusion
from src.core.rag.hybrid import build_lexical_query
from src.core.rag.ingest import DocumentParseError, DocumentParser
from src.core.rag.media_ingest import parse_csv_to_chunks


@pytest.mark.parametrize("query", [
    "what's the travel policy?",
    "C++ & (rust) | !bang 'quote' :colon",
    "100% refund <script>",
])
def test_lexical_query_is_always_safe_tsquery_syntax(query):
    q = build_lexical_query(query)
    # Only alphanumerics joined by " | " can reach to_tsquery
    assert all(tok.isalnum() for tok in q.split(" | ") if tok)


def test_lexical_query_drops_short_tokens_and_duplicates():
    assert build_lexical_query("Leave leave policy is ok") == "leave | policy"
    assert build_lexical_query("a b ?") == ""


def test_chunker_keeps_each_chunk_in_its_own_section():
    md = "Intro text.\n\n# Benefits\n\nDental is covered.\n\n## Travel\n\nFlights are economy."
    chunks = DocumentParser().chunk_markdown(md, "handbook.md")
    by_section = {c["section_title"]: c["chunk_text"] for c in chunks}
    assert by_section["Introduction"] == "Intro text."
    assert by_section["Benefits"] == "Dental is covered."
    assert by_section["Travel"] == "Flights are economy."
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunker_splits_long_sections_with_overlap():
    parser = DocumentParser(target_chunk_chars=100, overlap_chars=20)
    text = "# Long\n\n" + " ".join(f"word{i}" for i in range(200))
    chunks = parser.chunk_markdown(text, "long.md")
    assert len(chunks) > 3
    assert all(c["section_title"] == "Long" for c in chunks)
    assert all(len(c["chunk_text"]) <= 100 for c in chunks)


def test_binary_text_file_is_rejected(tmp_path: Path):
    f = tmp_path / "fake.txt"
    f.write_bytes(b"\x00\x01\x02binary\x00data")
    with pytest.raises(DocumentParseError):
        DocumentParser().parse_to_markdown(f, "fake.txt")


def test_utf8_text_file_is_read(tmp_path: Path):
    f = tmp_path / "notes.md"
    f.write_text("# Título\n\nCafé ☕", encoding="utf-8")
    assert "Café ☕" in DocumentParser().parse_to_markdown(f, "notes.md")


def test_tsv_uses_tab_delimiter(tmp_path: Path):
    f = tmp_path / "data.tsv"
    f.write_text("name\tcity\nAsha\tPune\n", encoding="utf-8")
    chunks = parse_csv_to_chunks(f, "data.tsv")
    assert "name: Asha | city: Pune" in chunks[0]["chunk_text"]


def test_rrf_prefers_documents_found_by_both_retrievers():
    dense = [{"chunk_id": "a", "score": 0.9, "retrieval_type": "dense"},
             {"chunk_id": "b", "score": 0.8, "retrieval_type": "dense"}]
    bm25 = [{"chunk_id": "b", "score": 0.3, "retrieval_type": "bm25"},
            {"chunk_id": "c", "score": 0.2, "retrieval_type": "bm25"}]
    fused = reciprocal_rank_fusion([dense, bm25], k=60)
    assert [d["chunk_id"] for d in fused][0] == "b"
    assert {d["chunk_id"] for d in fused} == {"a", "b", "c"}
