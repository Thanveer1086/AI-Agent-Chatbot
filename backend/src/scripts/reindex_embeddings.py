"""Re-embed all stored chunks and approved answers with the configured EMBEDDING_PROVIDER.

Usage (inside the backend container):
    python -m src.scripts.reindex_embeddings          # re-index now
    python -m src.scripts.reindex_embeddings --check  # only report the index status

Then restart the backend so the running server sees the new index:
    docker compose restart backend
"""
import argparse
import asyncio
import json
import logging

from src.core.db.session import db_manager
from src.core.rag import index_admin


async def main(check_only: bool) -> None:
    await db_manager.connect()
    try:
        status = await index_admin.check_index()
        print(json.dumps(status, indent=2, default=str))
        if check_only:
            return
        if status["compatible"]:
            print("Index already matches the configured provider; re-embedding anyway to be safe.")
        result = await index_admin.reindex_all()
        print("Re-index complete:", json.dumps(result))
        print("Now restart the backend:  docker compose restart backend")
    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report status, change nothing")
    asyncio.run(main(parser.parse_args().check))
