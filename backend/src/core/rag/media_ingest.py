"""Tabular (CSV, TSV, Excel) Ingestion Utilities."""
import csv
import logging
from typing import Any, Dict, Iterable, List, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


def _rows_to_chunks(
    headers: Sequence[str],
    rows: Iterable[Dict[str, Any]],
    filename: str,
    label: str = "",
    rows_per_chunk: int = 15,
    start_index: int = 0,
) -> List[Dict[str, Any]]:
    """Group row dicts into natural-language chunks of `rows_per_chunk` rows."""
    chunks: List[Dict[str, Any]] = []
    buffer: List[str] = []
    first_row = 1
    row_no = 0
    prefix = f"Dataset: {filename}{f' / {label}' if label else ''}\nHeaders: {', '.join(headers)}\n\n"

    def flush(last_row: int):
        chunks.append({
            "chunk_index": start_index + len(chunks),
            "chunk_text": prefix + "\n".join(buffer),
            "section_title": f"{label + ' ' if label else ''}Rows {first_row} - {last_row}",
            "filename": filename,
        })

    for row in rows:
        row_no += 1
        pairs = [f"{k}: {v}" for k, v in row.items() if k and v is not None and str(v).strip()]
        if pairs:
            buffer.append(" | ".join(pairs))
        if len(buffer) >= rows_per_chunk:
            flush(row_no)
            buffer = []
            first_row = row_no + 1

    if buffer:
        flush(row_no)
    return chunks


def parse_csv_to_chunks(file_path: Path, filename: str, rows_per_chunk: int = 15) -> List[Dict[str, Any]]:
    """Convert CSV/TSV rows to structured natural language chunks."""
    delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
    try:
        with open(file_path, mode="r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            return _rows_to_chunks(reader.fieldnames or [], reader, filename, rows_per_chunk=rows_per_chunk)
    except Exception as e:
        logger.error(f"CSV ingestion failed: {e}")
        return []


def parse_xlsx_to_chunks(file_path: Path, filename: str, rows_per_chunk: int = 15) -> List[Dict[str, Any]]:
    """Convert every worksheet of an .xlsx workbook into row chunks."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.error("openpyxl is not installed; cannot read .xlsx files.")
        return []

    chunks: List[Dict[str, Any]] = []
    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header_row = next(rows, None)
            if not header_row:
                continue
            headers = [str(h) if h is not None else f"Column{i + 1}" for i, h in enumerate(header_row)]
            row_dicts = (dict(zip(headers, r)) for r in rows)
            chunks.extend(_rows_to_chunks(headers, row_dicts, filename, label=ws.title,
                                          rows_per_chunk=rows_per_chunk, start_index=len(chunks)))
        wb.close()
    except Exception as e:
        logger.error(f"XLSX ingestion failed: {e}")
        return []
    return chunks
