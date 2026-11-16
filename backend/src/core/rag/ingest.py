"""Document Ingestion & Semantic Chunking (Docling + Markdown Splitter)."""
import os
import re
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class DocumentParser:
    def __init__(self, target_chunk_chars: int = 1500, overlap_chars: int = 200):
        self.target_chunk_chars = target_chunk_chars
        self.overlap_chars = overlap_chars

    def parse_to_markdown(self, file_path: Path, filename: str) -> str:
        """Parse PDF/Word/Text into structured markdown."""
        ext = file_path.suffix.lower()

        # Direct Word .docx extraction via standard library zipfile (robust & instant)
        if ext in [".docx", ".doc"]:
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    paragraphs = []
                    for p in tree.iterfind('.//w:p', namespaces):
                        texts = [node.text for node in p.iterfind('.//w:t', namespaces) if node.text]
                        if texts:
                            line = "".join(texts).strip()
                            if line:
                                paragraphs.append(line)
                    if paragraphs:
                        logger.info(f"Extracted {len(paragraphs)} paragraphs from {filename}")
                        return "\n\n".join(paragraphs)
            except Exception as e:
                logger.warning(f"Native docx extraction fallback: {e}")

        # PDF and Word via Docling if available
        if ext in [".pdf", ".docx", ".doc"]:
            try:
                from docling.document_converter import DocumentConverter
                logger.info(f"Converting {filename} using Docling...")
                converter = DocumentConverter()
                result = converter.convert(file_path)
                return result.document.export_to_markdown()
            except Exception as e:
                logger.warning(f"Docling conversion unavailable or failed ({e}). Falling back to text extraction.")

        # Text and Markdown direct read
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to read file text: {e}")
            return ""

    def chunk_markdown(self, markdown_text: str, filename: str) -> List[Dict[str, Any]]:
        """Split markdown into structure-aware chunks carrying section metadata."""
        if not markdown_text:
            return []

        chunks: List[Dict[str, Any]] = []
        # Split by markdown headers (#, ##, ###)
        sections = re.split(r"(^#{1,3}\s+.+$)", markdown_text, flags=re.MULTILINE)

        current_section = "Introduction"
        buffer = ""
        chunk_idx = 0

        for part in sections:
            if not part.strip():
                continue

            if part.startswith("#"):
                current_section = part.strip().lstrip("#").strip()
                continue

            buffer += part + "\n"

            # When buffer exceeds target size, create bounded chunk
            while len(buffer) >= self.target_chunk_chars:
                split_point = buffer.rfind("\n", 0, self.target_chunk_chars)
                if split_point == -1 or split_point < self.target_chunk_chars // 2:
                    split_point = self.target_chunk_chars

                chunk_text = buffer[:split_point].strip()
                if chunk_text:
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "chunk_text": chunk_text,
                        "section_title": current_section,
                        "filename": filename
                    })
                    chunk_idx += 1

                buffer = buffer[split_point - self.overlap_chars:]

        # Remaining buffer
        if buffer.strip():
            chunks.append({
                "chunk_index": chunk_idx,
                "chunk_text": buffer.strip(),
                "section_title": current_section,
                "filename": filename
            })

        return chunks

doc_parser = DocumentParser()
