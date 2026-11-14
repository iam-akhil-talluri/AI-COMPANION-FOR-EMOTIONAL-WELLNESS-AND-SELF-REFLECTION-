"""Find the approved passages most relevant to a user's message.

The local index is rebuilt automatically when the documents or the embedding
model change. Rebuild (or sync File Search) by hand:
    python -m src.retriever --rebuild
Try a query:
    python -m src.retriever "I can't sleep because I'm worried"
"""

import argparse
import hashlib
import json
import logging

from .chunking import chunk_documents
from .config import Settings, get_settings
from .document_loader import Document, load_documents
from .embedding import Embedder, get_client
from .vector_store import LocalVectorStore, OpenAIFileSearchStore, SearchResult

logger = logging.getLogger(__name__)


def fingerprint(documents: list[Document], model: str, max_chars: int) -> str:
    raw = json.dumps({"model": model, "max": max_chars,
                      "docs": [[d.document_id, d.title, d.source_url, d.text] for d in documents]})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Retriever:
    def __init__(self, settings: Settings | None = None, embedder: Embedder | None = None):
        self.settings = settings or get_settings()
        self.embedder = embedder or Embedder(self.settings.embedding_model)
        self._local: LocalVectorStore | None = None
        self._file_search: OpenAIFileSearchStore | None = None

    @property
    def backend(self) -> str:
        return self.settings.vector_backend

    # ----- local -----

    def build_local(self) -> LocalVectorStore:
        s = self.settings
        documents = load_documents(s.documents_dir)
        chunks = chunk_documents(documents, s.max_chunk_chars)
        vectors = self.embedder.embed([f"{c.title}\n\n{c.text}" for c in chunks])
        store = LocalVectorStore(chunks, vectors, fingerprint(documents, s.embedding_model, s.max_chunk_chars),
                                 s.embedding_model)
        store.save(s.embeddings_path, s.index_path)
        logger.info("Local index built: %d chunks from %d documents", len(chunks), len(documents))
        self._local = store
        return store

    def local_store(self) -> LocalVectorStore:
        if self._local is not None:
            return self._local
        s = self.settings
        expected = fingerprint(load_documents(s.documents_dir), s.embedding_model, s.max_chunk_chars)
        try:
            store = LocalVectorStore.load(s.embeddings_path, s.index_path)
            if store.fingerprint == expected:
                self._local = store
                return store
            logger.info("Documents changed: rebuilding the local index")
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            logger.info("No local index yet: building it")
        return self.build_local()

    # ----- OpenAI File Search -----

    def file_search_store(self) -> OpenAIFileSearchStore:
        if self._file_search is None:
            self._file_search = OpenAIFileSearchStore(
                get_client(), self.settings.vector_store_id, self.settings.file_search_state_path
            )
        return self._file_search

    def sync_file_search(self) -> dict:
        return self.file_search_store().sync(load_documents(self.settings.documents_dir))

    # ----- shared -----

    def rebuild(self) -> dict:
        if self.backend == "openai_file_search":
            return self.sync_file_search()
        store = self.build_local()
        return {"backend": "local", "chunks": len(store.chunks)}

    def retrieve(self, query: str) -> list[SearchResult]:
        s = self.settings
        if self.backend == "openai_file_search":
            return self.file_search_store().search(query, s.top_k, s.file_search_min_score)
        if self.backend != "local":
            raise ValueError(f"unknown VECTOR_BACKEND {self.backend!r}")
        store = self.local_store()
        if not store.chunks:
            return []
        return store.search(self.embedder.embed_one(query), s.top_k, s.local_min_score)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="python -m src.retriever")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the local index / sync File Search")
    parser.add_argument("--backend", choices=["local", "openai_file_search"])
    args = parser.parse_args()

    settings = get_settings()
    if args.backend:
        settings.vector_backend = args.backend
    retriever = Retriever(settings)
    if args.rebuild:
        print(json.dumps(retriever.rebuild(), indent=2))
    if args.query:
        for r in retriever.retrieve(args.query):
            print(f"{r.score:.3f}  {r.chunk_id:22} {r.title}\n       {r.text[:140]!r}")
    if not (args.rebuild or args.query):
        parser.print_help()


if __name__ == "__main__":
    main()
