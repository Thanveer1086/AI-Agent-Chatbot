"""Tabular (CSV, Excel) and Media Ingestion Utilities."""
import csv
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

def parse_csv_to_chunks(file_path: Path, filename: str, rows_per_chunk: int = 15) -> List[Dict[str, Any]]:
    """Convert CSV rows to structured natural language chunks."""
    chunks = []
    try:
        with open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            row_buffer = []
            chunk_idx = 0

            for row in reader:
                pairs = [f"{k}: {v}" for k, v in row.items() if v and v.strip()]
                if pairs:
                    row_buffer.append(" | ".join(pairs))

                if len(row_buffer) >= rows_per_chunk:
                    text = f"Dataset: {filename}\nHeaders: {', '.join(headers)}\n\n" + "\n".join(row_buffer)
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "chunk_text": text,
                        "section_title": f"Rows {chunk_idx * rows_per_chunk + 1} - {(chunk_idx + 1) * rows_per_chunk}",
                        "filename": filename
                    })
                    chunk_idx += 1
                    row_buffer = []

            if row_buffer:
                text = f"Dataset: {filename}\nHeaders: {', '.join(headers)}\n\n" + "\n".join(row_buffer)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "chunk_text": text,
                    "section_title": f"Rows {chunk_idx * rows_per_chunk + 1} - End",
                    "filename": filename
                })
    except Exception as e:
        logger.error(f"CSV ingestion failed: {e}")

    return chunks
