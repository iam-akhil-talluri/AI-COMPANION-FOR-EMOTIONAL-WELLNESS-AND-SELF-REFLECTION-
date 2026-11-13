"""Rebuild the RAG index from data/knowledge_base.json.

Run from the backend folder:  python -m app.ingest
"""

import asyncio
import logging

from .rag import build_index


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    index = asyncio.run(build_index())
    print(f"Indexed {len(index['chunks'])} chunks with {index['embeddingModel']}")


if __name__ == "__main__":
    main()
