"""RAG building blocks: lexical query builder, chunking, parsing, fusion."""
from pathlib import Path

import pytest

from src.core.rag.fusion import reciprocal_rank_fusion
from src.core.rag.hybrid import build_lexical_query
from src.core.rag.ingest import DocumentParseError, DocumentParser, strip_context_header
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


RULES_DOC = """# Rules Handbook

## RULE-A: Leave
### Business Answer
Employees get 24 days of annual leave.
### Conditions
Applies after probation.

## RULE-B: Travel
### Business Answer
Flights are economy class.
### Conditions
Domestic trips only.
"""


def test_small_sections_are_merged_under_their_parent():
    chunks = DocumentParser(target_chunk_chars=120).chunk_markdown(RULES_DOC, "rules.md")
    bodies = [strip_context_header(c["chunk_text"]) for c in chunks]
    # Each rule's small sub-sections end up together, with their sub-headings kept
    leave = next(b for b in bodies if "24 days" in b)
    assert "Applies after probation" in leave and "### Conditions" in leave
    # ...but two different rules are never mixed in one chunk
    assert not any("24 days" in b and "economy" in b for b in bodies)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_every_chunk_has_a_context_header_naming_its_section():
    chunks = DocumentParser(target_chunk_chars=120).chunk_markdown(RULES_DOC, "rules.md")
    travel = next(c for c in chunks if "economy" in c["chunk_text"])
    first_line = travel["chunk_text"].split("\n")[0]
    assert first_line == "Document: rules | Section: Rules Handbook > RULE-B: Travel"
    assert travel["section_title"] == "RULE-B: Travel"  # document-title H1 dropped from the label


def test_whole_document_fits_in_one_chunk_when_small():
    chunks = DocumentParser(target_chunk_chars=1500).chunk_markdown(RULES_DOC, "rules.md")
    assert len(chunks) == 1
    assert "RULE-A" in chunks[0]["chunk_text"] and "RULE-B" in chunks[0]["chunk_text"]


def test_tiny_intro_is_attached_to_the_next_chunk():
    md = "Company Guide\n\n# Big Section\n\n" + ("Long policy text. " * 120)
    chunks = DocumentParser(target_chunk_chars=500).chunk_markdown(md, "guide.md")
    assert "Company Guide" in strip_context_header(chunks[0]["chunk_text"])
    assert all(len(strip_context_header(c["chunk_text"])) > 100 for c in chunks)


def test_chunker_splits_long_sections_with_overlap():
    parser = DocumentParser(target_chunk_chars=100, overlap_chars=20)
    text = "# Long\n\n" + " ".join(f"word{i}" for i in range(200))
    chunks = parser.chunk_markdown(text, "long.md")
    assert len(chunks) > 3
    assert all(c["section_title"] == "Long" for c in chunks)
    # Body respects the size limit (allowance for an attached short intro); header is extra
    assert all(len(strip_context_header(c["chunk_text"])) <= 100 + parser.MIN_CHUNK_CHARS for c in chunks)
    # Consecutive pieces overlap so no sentence is lost at a boundary
    first, second = (strip_context_header(c["chunk_text"]) for c in chunks[:2])
    assert first.split()[-1] in second


def test_headings_inside_code_blocks_are_not_split_points():
    md = "# Guide\n\n```bash\n# install\npip install x\n```\n\nDone."
    chunks = DocumentParser().chunk_markdown(md, "g.md")
    assert len(chunks) == 1 and "# install" in chunks[0]["chunk_text"]


def _bodies(chunks):
    return [strip_context_header(c["chunk_text"]) for c in chunks]


def test_big_table_is_split_by_rows_with_header_repeated():
    rows = "\n".join(f"| RULE-{i:03d} | Value number {i} for this rule |" for i in range(80))
    md = f"# Rules\n\n## Rule Table\n\n| Rule | Description |\n| --- | --- |\n{rows}\n"
    chunks = DocumentParser(target_chunk_chars=600).chunk_markdown(md, "t.md")
    bodies = _bodies(chunks)
    assert len(chunks) > 3
    for body in bodies:
        lines = body.splitlines()
        assert lines[0] == "| Rule | Description |" and lines[1] == "| --- | --- |"
        assert all(line.startswith("| ") and line.endswith(" |") for line in lines)  # no cut rows
    # Every row appears exactly once (tables get no overlap)
    all_rows = [line for b in bodies for line in b.splitlines()[2:]]
    assert len(all_rows) == 80 and len(set(all_rows)) == 80


def test_heading_stays_with_the_table_after_it():
    rows = "\n".join(f"| {i} | row {i} |" for i in range(60))
    md = f"## Section\n\nIntro text.\n\n#### Pricing table\n\n| A | B |\n| - | - |\n{rows}\n"
    chunks = DocumentParser(target_chunk_chars=400).chunk_markdown(md, "t.md")
    bodies = _bodies(chunks)
    table_start = next(b for b in bodies if "| 0 | row 0 |" in b)
    assert "#### Pricing table" in table_start
    assert not any(b.strip().endswith("#### Pricing table") for b in bodies)


def test_big_code_block_is_split_by_lines_with_fences_kept():
    code = "\n".join(f"print('line {i}')  # step {i}" for i in range(120))
    md = f"## Script\n\n```python\n{code}\n```\n"
    chunks = DocumentParser(target_chunk_chars=500).chunk_markdown(md, "c.md")
    bodies = _bodies(chunks)
    assert len(chunks) > 3
    for body in bodies:
        assert body.startswith("```python\n") and body.endswith("\n```")
    lines = [line for b in bodies for line in b.splitlines() if line.startswith("print")]
    assert len(lines) == 120


def test_long_prose_is_split_at_sentence_boundaries():
    para = " ".join(f"Sentence number {i} explains one rule clearly." for i in range(80))
    chunks = DocumentParser(target_chunk_chars=400).chunk_markdown(f"## Policy\n\n{para}", "p.md")
    bodies = _bodies(chunks)
    assert len(chunks) > 3
    assert all(b.rstrip().endswith(".") for b in bodies)
    assert all(b.lstrip().startswith("Sentence") for b in bodies)


def test_final_chunk_never_exceeds_hard_limit_including_header():
    long_title = "A very long section heading " * 6
    md = f"# Doc\n\n## {long_title}\n\n" + ("Words in a paragraph here. " * 300)
    parser = DocumentParser(target_chunk_chars=1500, max_chunk_chars=1600)
    chunks = parser.chunk_markdown(md, "limits.md")
    assert chunks and all(len(c["chunk_text"]) <= 1600 for c in chunks)


def test_heading_only_and_separator_chunks_are_dropped():
    md = "# Doc\n\n## Empty Section\n\n---\n\n## Real\n\nActual content here.\n\n---\n"
    chunks = DocumentParser(target_chunk_chars=30).chunk_markdown(md, "d.md")
    bodies = _bodies(chunks)
    assert bodies == ["Actual content here."]


def test_tilde_fences_protect_headings_too():
    md = "# Guide\n\n~~~\n# not a heading\n~~~\n\nDone."
    chunks = DocumentParser().chunk_markdown(md, "g.md")
    assert len(chunks) == 1 and "# not a heading" in chunks[0]["chunk_text"]


def _make_docx(path: Path, body_xml: str) -> None:
    import zipfile
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document {ns}><w:body>{body_xml}</w:body></w:document>')


def test_docx_tables_headings_and_lists_become_markdown(tmp_path: Path):
    def p(text, style=None, numbered=False):
        ppr = ""
        if style or numbered:
            ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
                  ('<w:numPr><w:ilvl w:val="0"/></w:numPr>' if numbered else "") + "</w:pPr>"
        return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"

    def row(*cells):
        return "<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in cells) + "</w:tr>"

    f = tmp_path / "guide.docx"
    _make_docx(f, p("Leave Policy", "Heading1") + p("Annual leave", numbered=True)
               + f"<w:tbl>{row('Type', 'Days')}{row('Annual', '24')}{row('Sick', '12')}</w:tbl>")
    md = DocumentParser().parse_to_markdown(f, "guide.docx")
    assert "# Leave Policy" in md
    assert "- Annual leave" in md
    assert "| Type | Days |\n| --- | --- |\n| Annual | 24 |\n| Sick | 12 |" in md


def test_strip_context_header():
    assert strip_context_header("Document: a | Section: b\n\nBody text") == "Body text"
    assert strip_context_header("No header here") == "No header here"


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


def test_relevance_score_is_always_between_0_and_1():
    from src.core.rag.tool import relevance_score

    # Raw CrossEncoder logits (the -367% / -460% bug) become probabilities
    assert relevance_score({"rerank_score": -4.6}) == 0.01
    assert relevance_score({"rerank_score": -3.67}) == 0.02
    assert relevance_score({"rerank_score": 0.0}) == 0.5
    assert relevance_score({"rerank_score": 6.0}) == 1.0
    # Vector-only results use cosine similarity
    assert relevance_score({"retrieval_type": "dense", "score": 0.55}) == 0.55
    # Keyword-only without reranker: share of the best possible fused score
    assert relevance_score({"retrieval_type": "bm25", "score": 0.05, "fused_score": 1 / 61}, rrf_k=60) == 0.5
    for p in ({"rerank_score": -50}, {"rerank_score": 50}, {"retrieval_type": "dense", "score": -0.2}):
        assert 0.0 <= relevance_score(p) <= 1.0


def test_relevance_order_matches_reranker_order():
    from src.core.rag.tool import relevance_score

    logits = [2.1, -0.4, -3.7, -4.6]
    scores = [relevance_score({"rerank_score": s}) for s in logits]
    assert scores == sorted(scores, reverse=True)
