"""Document Ingestion & Semantic Chunking (Docling / pypdf + Markdown Splitter)."""
import re
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".log", ".html", ".htm", ".xml", ".yaml", ".yml"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".csv", ".tsv", ".xlsx"}


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


class DocumentParser:
    def __init__(self, target_chunk_chars: int = 1500, overlap_chars: int = 200):
        self.target_chunk_chars = target_chunk_chars
        self.overlap_chars = overlap_chars

    @staticmethod
    def _parse_docx(file_path: Path, filename: str) -> str:
        import zipfile
        import xml.etree.ElementTree as ET
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with zipfile.ZipFile(file_path) as z:
            tree = ET.fromstring(z.read("word/document.xml"))
        paragraphs = []
        for p in tree.iterfind(".//w:p", ns):
            line = "".join(n.text for n in p.iterfind(".//w:t", ns) if n.text).strip()
            if not line:
                continue
            # Keep Word heading styles as markdown headings so chunks get section titles.
            style = p.find("./w:pPr/w:pStyle", ns)
            style_val = style.get(f"{{{ns['w']}}}val", "") if style is not None else ""
            level = re.match(r"Heading(\d)", style_val)
            if level and int(level.group(1)) <= 3:
                line = "#" * int(level.group(1)) + " " + line
            paragraphs.append(line)
        logger.info(f"Extracted {len(paragraphs)} paragraphs from {filename}")
        return "\n\n".join(paragraphs)

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

    def _split_section(self, text: str, section: str, filename: str, start_idx: int) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        buffer = text
        idx = start_idx
        while len(buffer) > self.target_chunk_chars:
            split_point = buffer.rfind("\n", 0, self.target_chunk_chars)
            if split_point < self.target_chunk_chars // 2:
                split_point = buffer.rfind(" ", 0, self.target_chunk_chars)
            if split_point < self.target_chunk_chars // 2:
                split_point = self.target_chunk_chars

            chunk_text = buffer[:split_point].strip()
            if chunk_text:
                chunks.append({
                    "chunk_index": idx,
                    "chunk_text": chunk_text,
                    "section_title": section,
                    "filename": filename,
                })
                idx += 1
            buffer = buffer[max(split_point - self.overlap_chars, 1):]

        if buffer.strip():
            chunks.append({
                "chunk_index": idx,
                "chunk_text": buffer.strip(),
                "section_title": section,
                "filename": filename,
            })
        return chunks

    def chunk_markdown(self, markdown_text: str, filename: str) -> List[Dict[str, Any]]:
        """Split markdown into structure-aware chunks carrying correct section metadata.

        Each section is chunked on its own, so a chunk never mixes text from two
        sections or carries the wrong heading.
        """
        if not markdown_text:
            return []

        parts = re.split(r"(^#{1,3}\s+.+$)", markdown_text, flags=re.MULTILINE)
        chunks: List[Dict[str, Any]] = []
        current_section = "Introduction"

        for part in parts:
            if not part.strip():
                continue
            if re.match(r"^#{1,3}\s+", part):
                current_section = part.strip().lstrip("#").strip()
                continue
            chunks.extend(self._split_section(part, current_section, filename, len(chunks)))

        return chunks


doc_parser = DocumentParser()
