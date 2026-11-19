"""Document Ingestion & Structure-Aware Chunking (Docling / pypdf + heading-tree packing)."""
import re
import logging
from typing import Any, Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".log", ".html", ".htm", ".xml", ".yaml", ".yml"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".csv", ".tsv", ".xlsx"}

HEADER_PREFIX = "Document: "

# Markdown building blocks recognised by the chunker
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
TABLE_LINE_RE = re.compile(r"^\s*\|")
TABLE_SEPARATOR_RE = re.compile(r"^[\s|:-]*-[\s|:-]*$")
HEADING_LINE_RE = re.compile(r"^#{1,6}\s+\S")
THEMATIC_BREAK_RE = re.compile(r"^\s*(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$")
# End of a sentence: . ! or ? followed by whitespace and a capital letter, digit, quote or bracket
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# (text, joiner placed before it, may be repeated as overlap)
Atom = Tuple[str, str, bool]


class DocumentParseError(ValueError):
    """Raised when a document cannot be turned into usable text."""


def _looks_binary(data: bytes) -> bool:
    sample = data[:4096]
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError as e:
        # A multi-byte character cut off at the sample boundary is fine.
        return e.start < len(sample) - 4


def strip_context_header(chunk_text: str) -> str:
    """Return the chunk body without its 'Document: ... | Section: ...' header (for UI snippets)."""
    if chunk_text.startswith(HEADER_PREFIX):
        _, sep, body = chunk_text.partition("\n\n")
        if sep and body.strip():
            return body
    return chunk_text


# ---------------------------------------------------------------------- Word (.docx)
def _docx_text(element) -> str:
    """Visible text of a Word element; tabs become spaces and line breaks become newlines."""
    out: List[str] = []
    for node in element.iter():
        if node.tag == W_NS + "t" and node.text:
            out.append(node.text)
        elif node.tag == W_NS + "tab":
            out.append(" ")
        elif node.tag in (W_NS + "br", W_NS + "cr"):
            out.append("\n")
    return "".join(out).strip()


def _docx_paragraph(p) -> str:
    text = _docx_text(p)
    if not text:
        return ""
    ppr = p.find(W_NS + "pPr")
    style = ppr.find(W_NS + "pStyle") if ppr is not None else None
    style_val = style.get(W_NS + "val", "") if style is not None else ""
    # Keep Word heading styles as markdown headings so chunks get section titles.
    if style_val == "Title":
        return "# " + text.replace("\n", " ")
    level = re.match(r"Heading(\d)", style_val)
    if level and int(level.group(1)) <= 6:
        return "#" * int(level.group(1)) + " " + text.replace("\n", " ")
    # Bulleted / numbered list items
    num = ppr.find(W_NS + "numPr") if ppr is not None else None
    if num is not None:
        ilvl = num.find(W_NS + "ilvl")
        depth = int(ilvl.get(W_NS + "val", "0")) if ilvl is not None else 0
        return "  " * depth + "- " + text.replace("\n", " ")
    return text


def _docx_table(tbl) -> str:
    """Convert a Word table into a markdown table (the chunker can then split it by rows)."""
    rows: List[List[str]] = []
    for tr in tbl.findall(W_NS + "tr"):
        cells = []
        for tc in tr.findall(W_NS + "tc"):
            parts = [_docx_text(p) for p in tc.iter(W_NS + "p")]
            cell = " ".join(t for t in parts if t).replace("\n", " ").replace("|", "\\|").strip()
            cells.append(cell)
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    if width == 1:
        # A one-column table is a layout box, not data: keep it as plain paragraphs.
        return "\n\n".join(r[0] for r in rows if r[0])
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


class DocumentParser:
    def __init__(
        self,
        target_chunk_chars: int = 1500,
        overlap_chars: int = 200,
        max_split_level: int = 3,
        max_chunk_chars: int = 2000,
    ):
        self.target_chunk_chars = target_chunk_chars
        self.overlap_chars = overlap_chars
        # Headings up to this level split the document; deeper headings stay inside the text
        self.max_split_level = max_split_level
        # Hard limit for the FINAL chunk text including its context header. The reranker
        # (ms-marco-MiniLM) reads about 512 tokens (~2000 chars); longer text is cut off.
        self.max_chunk_chars = max(max_chunk_chars, target_chunk_chars)

    # ------------------------------------------------------------------ parsing
    @staticmethod
    def _parse_docx(file_path: Path, filename: str) -> str:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(file_path) as z:
            tree = ET.fromstring(z.read("word/document.xml"))
        body = tree.find(W_NS + "body")
        if body is None:
            return ""

        blocks: List[str] = []

        def walk(element) -> None:
            # Paragraphs and tables in document order (content controls are unwrapped)
            for child in element:
                if child.tag == W_NS + "p":
                    text = _docx_paragraph(child)
                elif child.tag == W_NS + "tbl":
                    text = _docx_table(child)
                elif child.tag in (W_NS + "sdt", W_NS + "sdtContent", W_NS + "customXml", W_NS + "smartTag"):
                    walk(child)
                    continue
                else:
                    continue
                if text:
                    blocks.append(text)

        walk(body)
        logger.info(f"Extracted {len(blocks)} blocks from {filename}")
        return "\n\n".join(blocks)

    @staticmethod
    def _parse_pdf(file_path: Path, filename: str) -> str:
        try:
            from docling.document_converter import DocumentConverter
            logger.info(f"Converting {filename} using Docling...")
            return DocumentConverter().convert(file_path).document.export_to_markdown()
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Docling failed on {filename} ({e}); falling back to pypdf.")

        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise DocumentParseError("No PDF parser installed (install docling or pypdf).") from e

        reader = PdfReader(str(file_path))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"## Page {i}\n\n{text}")
        if not pages:
            raise DocumentParseError(
                "The PDF contains no extractable text (it may be a scanned image; OCR is not enabled)."
            )
        return "\n\n".join(pages)

    def parse_to_markdown(self, file_path: Path, filename: str) -> str:
        """Parse PDF/Word/Text into structured markdown. Never returns binary garbage."""
        ext = file_path.suffix.lower()

        if ext == ".docx":
            try:
                text = self._parse_docx(file_path, filename)
                if text:
                    return text
            except Exception as e:
                logger.warning(f"Native docx extraction failed for {filename}: {e}")
            raise DocumentParseError("Could not extract text from the Word document.")

        if ext == ".pdf":
            return self._parse_pdf(file_path, filename)

        data = file_path.read_bytes()
        if _looks_binary(data):
            raise DocumentParseError(f"'{filename}' looks like a binary file, not text.")
        return data.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ chunking
    # Chunks follow the heading tree. A section that fits in `target_chunk_chars` becomes
    # ONE chunk together with all its sub-sections. A larger section has its small
    # sub-sections packed together in order, never mixing content from two different
    # parents (e.g. two business rules).
    #
    # Only a single piece of text that is too large on its own is split, and then along
    # its structure: paragraphs, whole tables and whole code blocks first; a big table is
    # split by rows with its header repeated; a big code block by whole lines with its
    # fences repeated; long prose at line, then sentence, then word boundaries, with
    # overlap made of whole sentences/words.
    #
    # Every chunk starts with a context header ("Document: X | Section: A > B") so the
    # embedding, keyword search, reranker and LLM all know where the text comes from.
    # The final text (header included) never exceeds `max_chunk_chars`, and chunks that
    # would only contain headings or `---` separators are dropped.

    @staticmethod
    def _doc_name(filename: str) -> str:
        return re.sub(r"\.[A-Za-z0-9]+$", "", filename)

    def _context_header(self, filename: str, path: List[str]) -> str:
        header = f"{HEADER_PREFIX}{self._doc_name(filename)}"
        if path:
            header += " | Section: " + " > ".join(path)
        return header

    @staticmethod
    def _section_title(path: List[str]) -> str:
        # A single document-title H1 adds nothing to "which section", so drop it when deeper levels exist
        shown = path[1:] if len(path) > 1 else path
        return " > ".join(shown) if shown else "Introduction"

    @staticmethod
    def _closes_fence(line: str, fence: str) -> bool:
        s = line.strip()
        return len(s) >= len(fence) and set(s) == {fence[0]}

    def _parse_tree(self, markdown_text: str) -> Dict[str, Any]:
        root: Dict[str, Any] = {"level": 0, "title": None, "text": "", "children": []}
        stack = [root]
        heading = re.compile(r"^(#{1,%d})\s+(.+?)\s*#*\s*$" % self.max_split_level)
        fence = None
        for line in markdown_text.splitlines():
            if fence:
                if self._closes_fence(line, fence):
                    fence = None
                stack[-1]["text"] += line + "\n"
                continue
            opened = FENCE_RE.match(line)
            if opened:
                fence = opened.group(1)
                stack[-1]["text"] += line + "\n"
                continue
            match = heading.match(line)
            if match:
                node = {"level": len(match.group(1)), "title": match.group(2).strip(), "text": "", "children": []}
                while stack[-1]["level"] >= node["level"]:
                    stack.pop()
                stack[-1]["children"].append(node)
                stack.append(node)
            else:
                stack[-1]["text"] += line + "\n"
        return root

    def _render(self, node: Dict[str, Any], include_heading: bool = True) -> str:
        parts = []
        if include_heading and node["title"]:
            parts.append("#" * node["level"] + " " + node["title"])
        if node["text"].strip():
            parts.append(node["text"].strip())
        for child in node["children"]:
            rendered = self._render(child)
            if rendered:
                parts.append(rendered)
        return "\n\n".join(parts)

    # ---------------------------------------------------- splitting one oversized text
    @staticmethod
    def _is_heading_only(block: str) -> bool:
        lines = [line for line in block.splitlines() if line.strip()]
        return bool(lines) and all(HEADING_LINE_RE.match(line) for line in lines)

    @staticmethod
    def _is_non_content(text: str) -> bool:
        """True when text holds only headings and/or decorative `---` separators."""
        lines = [line for line in text.splitlines() if line.strip()]
        if any(FENCE_RE.match(line) for line in lines):
            return False
        return all(HEADING_LINE_RE.match(line) or THEMATIC_BREAK_RE.match(line) for line in lines)

    @staticmethod
    def _strip_breaks(text: str) -> str:
        """Remove `---` separators (and blank lines) at the very start and end of a chunk."""
        lines = text.split("\n")
        while lines and (not lines[-1].strip() or THEMATIC_BREAK_RE.match(lines[-1])):
            lines.pop()
        while lines and (not lines[0].strip() or THEMATIC_BREAK_RE.match(lines[0])):
            lines.pop(0)
        return "\n".join(lines)

    def _atomic_units(self, text: str) -> List[Tuple[str, str]]:
        """Split text into (kind, block) units that are never cut while packing:
        paragraphs ("prose"), whole tables ("table") and whole fenced code blocks ("code").
        A heading-only unit is glued to the unit after it, so a heading never ends a chunk."""
        units: List[Tuple[str, str]] = []
        cur: List[str] = []
        kind = "prose"
        fence = None

        def flush() -> None:
            nonlocal cur
            block = "\n".join(cur).strip("\n")
            if block.strip():
                units.append((kind, block))
            cur = []

        for line in text.splitlines():
            if fence:
                cur.append(line)
                if self._closes_fence(line, fence):
                    fence = None
                    flush()
                    kind = "prose"
                continue
            opened = FENCE_RE.match(line)
            if opened:
                flush()
                kind, fence = "code", opened.group(1)
                cur.append(line)
                continue
            if TABLE_LINE_RE.match(line):
                if kind != "table":
                    flush()
                    kind = "table"
                cur.append(line)
                continue
            if kind == "table":
                flush()
                kind = "prose"
            if not line.strip():
                flush()
                continue
            cur.append(line)
        flush()  # an unclosed fence still ends up as one code unit

        glued: List[Tuple[str, str]] = []
        lead: List[str] = []
        for unit_kind, block in units:
            if unit_kind == "prose" and self._is_heading_only(block):
                lead.append(block)
                continue
            if lead:
                block = "\n\n".join(lead + [block])
                lead = []
            glued.append((unit_kind, block))
        if lead:
            glued.append(("prose", "\n\n".join(lead)))
        return glued

    @staticmethod
    def _hard_split(text: str, budget: int) -> List[str]:
        budget = max(budget, 1)
        return [text[i:i + budget] for i in range(0, len(text), budget)]

    def _group_lines(self, lines: List[str], first_budget: int, budget: int) -> List[str]:
        """Pack whole lines into groups; the first group may have a smaller budget."""
        groups: List[str] = []
        cur: List[str] = []
        size = 0
        for line in lines:
            limit = first_budget if not groups else budget
            if len(line) > limit:
                if cur:
                    groups.append("\n".join(cur))
                    cur, size = [], 0
                groups.extend(self._hard_split(line, limit))
                continue
            add = len(line) + (1 if cur else 0)
            if cur and size + add > limit:
                groups.append("\n".join(cur))
                cur, size = [line], len(line)
            else:
                cur.append(line)
                size += add
        if cur:
            groups.append("\n".join(cur))
        return groups

    def _split_table(self, block: str, budget: int) -> List[str]:
        """Split a markdown table by rows, repeating its header row(s) in every piece."""
        lines = block.split("\n")
        first = next(i for i, line in enumerate(lines) if TABLE_LINE_RE.match(line))
        lead = "\n".join(lines[:first]).strip()
        rows = [line for line in lines[first:] if line.strip()]
        header_rows = 2 if len(rows) > 1 and TABLE_SEPARATOR_RE.match(rows[1]) else 1
        header, body = "\n".join(rows[:header_rows]), rows[header_rows:]
        first_prefix = f"{lead}\n\n{header}" if lead else header
        first_budget = budget - len(first_prefix) - 1
        rest_budget = budget - len(header) - 1
        if not body or first_budget < 50 or rest_budget < 50:
            return self._hard_split(block, budget)
        groups = self._group_lines(body, first_budget, rest_budget)
        return [f"{first_prefix if i == 0 else header}\n{group}" for i, group in enumerate(groups)]

    def _split_code(self, block: str, budget: int) -> List[str]:
        """Split a fenced code block by whole lines, repeating the fences in every piece."""
        lines = block.split("\n")
        start = next(i for i, line in enumerate(lines) if FENCE_RE.match(line))
        lead = "\n".join(lines[:start]).strip()
        opening = lines[start]
        fence = FENCE_RE.match(opening).group(1)
        body = lines[start + 1:]
        if body and self._closes_fence(body[-1], fence):
            body = body[:-1]
        first_prefix = f"{lead}\n\n{opening}" if lead else opening
        first_budget = budget - len(first_prefix) - len(fence) - 2
        rest_budget = budget - len(opening) - len(fence) - 2
        if not body or first_budget < 50 or rest_budget < 50:
            return self._hard_split(block, budget)
        groups = self._group_lines(body, first_budget, rest_budget)
        return [f"{first_prefix if i == 0 else opening}\n{group}\n{fence}" for i, group in enumerate(groups)]

    def _prose_atoms(self, text: str, budget: int, joiner: str) -> List[Atom]:
        """Break prose into pieces <= budget at line, then sentence, then word boundaries."""
        if len(text) <= budget:
            return [(text, joiner, True)]
        for splitter, sep in (
            (lambda t: t.split("\n"), "\n"),
            (SENTENCE_END_RE.split, " "),
            (str.split, " "),
        ):
            parts = [part for part in splitter(text) if part.strip()]
            if len(parts) > 1:
                atoms: List[Atom] = []
                for i, part in enumerate(parts):
                    atoms.extend(self._prose_atoms(part, budget, joiner if i == 0 else sep))
                return atoms
        return [(piece, joiner if i == 0 else "", True) for i, piece in enumerate(self._hard_split(text, budget))]

    @staticmethod
    def _join(atoms: List[Atom]) -> str:
        return "".join((joiner if i else "") + text for i, (text, joiner, _) in enumerate(atoms))

    def _pack(self, atoms: List[Atom], budget: int) -> List[str]:
        """Greedily pack atoms into chunks <= budget. A new chunk starts with the last few
        prose atoms of the previous one (whole sentences/words, up to overlap_chars)."""
        chunks: List[str] = []
        buf: List[Atom] = []
        for atom in atoms:
            candidate = buf + [atom]
            if buf and len(self._join(candidate)) > budget:
                chunks.append(self._join(buf))
                tail: List[Atom] = []
                for prev in reversed(buf):
                    if not prev[2] or len(self._join([prev] + tail)) > self.overlap_chars:
                        break
                    tail.insert(0, prev)
                if len(tail) == len(buf):  # never repeat a whole chunk
                    tail = []
                while tail and len(self._join(tail + [atom])) > budget:
                    tail.pop(0)
                candidate = tail + [atom]
            buf = candidate
        if buf:
            chunks.append(self._join(buf))
        return chunks

    def _split_text(self, text: str, budget: int) -> List[str]:
        """Split one piece of text that is too large into structure-respecting pieces."""
        budget = max(budget, 50)
        text = text.strip()
        if len(text) <= budget:
            return [text] if text else []
        atoms: List[Atom] = []
        for kind, block in self._atomic_units(text):
            if len(block) <= budget:
                atoms.append((block, "\n\n", kind == "prose"))
            elif kind == "table":
                atoms.extend((piece, "\n\n", False) for piece in self._split_table(block, budget))
            elif kind == "code":
                atoms.extend((piece, "\n\n", False) for piece in self._split_code(block, budget))
            else:
                atoms.extend(self._prose_atoms(block, budget, "\n\n"))
        return [chunk.strip() for chunk in self._pack(atoms, budget) if chunk.strip()]

    # ------------------------------------------------------------ heading-tree packing
    # Text shorter than this (e.g. a lone title line) is attached to the next chunk instead
    # of becoming a tiny chunk on its own.
    MIN_CHUNK_CHARS = 300

    def _chunk_node(self, node: Dict[str, Any], path: List[str], prefix: str = "") -> List[Tuple[List[str], str]]:
        """Return (heading path, body text) pairs for a node and everything below it.

        `prefix` is short text from just before this node that is prepended to its first chunk.
        """
        whole = self._render(node, include_heading=False)
        if not whole.strip():
            return [(path, prefix)] if prefix.strip() else []
        # A carried-over intro (< MIN_CHUNK_CHARS) may push a chunk slightly past the target
        limit = self.target_chunk_chars + (self.MIN_CHUNK_CHARS if prefix else 0)
        if len(whole) + len(prefix) <= limit:
            return [(path, f"{prefix}\n\n{whole}" if prefix else whole)]

        # Too big for one chunk: pack the node's own intro text and its children, in order.
        items: List[Tuple[List[str], str, Any]] = []
        if node["text"].strip():
            items.append((path, node["text"].strip(), None))
        for child in node["children"]:
            items.append((path + [child["title"]], self._render(child), child))

        out: List[Tuple[List[str], str]] = []
        buffer: List[str] = [prefix] if prefix.strip() else []
        buffer_paths: List[List[str]] = [path] if prefix.strip() else []

        def flush() -> None:
            if buffer:
                # One item keeps its own path; several packed siblings share the parent's path
                chunk_path = buffer_paths[0] if len(buffer) == 1 else path
                out.append((chunk_path, "\n\n".join(buffer)))
                buffer.clear()
                buffer_paths.clear()

        for item_path, text, child in items:
            if self._is_non_content(text):
                continue  # an empty section (only its heading / `---`) adds nothing
            if len(text) > self.target_chunk_chars:
                # A tiny pending buffer (e.g. a title line) rides along into the big item
                carry = ""
                if buffer and sum(len(b) for b in buffer) < self.MIN_CHUNK_CHARS:
                    carry = "\n\n".join(buffer)
                    buffer.clear()
                    buffer_paths.clear()
                flush()
                if child is not None:
                    out.extend(self._chunk_node(child, item_path, prefix=carry))
                else:
                    pieces = self._split_text(text, self.target_chunk_chars)
                    if carry and pieces:
                        pieces[0] = f"{carry}\n\n{pieces[0]}"
                    out.extend((item_path, piece) for piece in pieces)
                continue
            projected = sum(len(b) for b in buffer) + 2 * len(buffer) + len(text)
            if buffer and projected > self.target_chunk_chars:
                flush()
            buffer.append(text)
            buffer_paths.append(item_path)
        flush()
        return out

    def chunk_markdown(self, markdown_text: str, filename: str) -> List[Dict[str, Any]]:
        """Split markdown into structure-aware chunks, each prefixed with a context header."""
        if not markdown_text or not markdown_text.strip():
            return []

        chunks: List[Dict[str, Any]] = []
        for path, body in self._chunk_node(self._parse_tree(markdown_text), []):
            body = self._strip_breaks(body.strip())
            if not body or self._is_non_content(body):
                continue
            header = self._context_header(filename, path)
            # Hard limit: header + body must fit in max_chunk_chars
            room = self.max_chunk_chars - len(header) - 2
            pieces = [body] if len(body) <= room else self._split_text(body, max(room, 200))
            for piece in pieces:
                piece = self._strip_breaks(piece)
                if not piece or self._is_non_content(piece):
                    continue
                chunks.append({
                    "chunk_index": len(chunks),
                    "chunk_text": f"{header}\n\n{piece}",
                    "section_title": self._section_title(path),
                    "filename": filename,
                })
        return chunks


doc_parser = DocumentParser()
