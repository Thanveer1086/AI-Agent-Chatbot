"""Re-chunk every uploaded document from its stored original file (after chunking changes).

Usage (inside the backend container):
    python -m src.scripts.rechunk_documents

No re-upload is needed. Each file keeps its enabled/disabled state and applications.
"""
import asyncio
import json
import logging

from src.core.db.session import db_manager
from src.core.rag import index_admin
from src.core.rag.rechunk import rechunk_all


async def main() -> None:
    await db_manager.connect()
    try:
        await index_admin.check_index()
        result = await rechunk_all()
        print(json.dumps(result, indent=2, default=str))
        if result["failed"]:
            print(f"{len(result['failed'])} file(s) failed; their previous chunks were kept.")
    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())
