"""Offline tests: embeddings and the chat model are replaced with fakes."""

import os
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from src import rag_pipeline  # noqa: E402
from src.chunking import chunk_documents, chunk_text  # noqa: E402
from src.config import Settings  # noqa: E402
from src.document_loader import Document, load_documents, parse_front_matter  # noqa: E402
from src.retriever import Retriever  # noqa: E402
from src.vector_store import LocalVectorStore, OpenAIFileSearchStore, SearchResult, content_hash, plan_sync  # noqa: E402

VOCAB = ["breath", "sleep", "exam", "lonely", "journal"]


class FakeEmbedder:
    """Bag-of-keywords vectors: enough to test ranking without the API."""
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        rows = np.array([[float(w in t.lower()) for w in VOCAB] + [0.01] for t in texts], dtype=np.float32)
        return rows / np.linalg.norm(rows, axis=1, keepdims=True)

    def embed_one(self, text):
        return self.embed([text])[0]


def write_doc(directory, doc_id, title, body, approved="true"):
    (directory / f"{doc_id}.md").write_text(
        f"---\ndocumentId: {doc_id}\ntitle: {title}\nsourceUrl: \napproved: {approved}\n---\n\n# {title}\n\n{body}\n",
        encoding="utf-8")


@pytest.fixture
def settings(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    write_doc(docs, "d-breath", "Breathing", "Slow breath out.\n\nBox breath for four.")
    write_doc(docs, "d-sleep", "Sleep", "Keep a sleep routine.")
    write_doc(docs, "d-hidden", "Hidden", "Unreviewed breath advice.", approved="false")
    return Settings(openai_api_key="test", vector_backend="local", top_k=3, local_min_score=0.3,
                    documents_dir=docs, embeddings_path=tmp_path / "emb.npy", index_path=tmp_path / "index.json",
                    file_search_state_path=tmp_path / "fs.json")


# ---------- Loading and chunking ----------

def test_front_matter_is_parsed():
    meta, body = parse_front_matter("---\ntitle: A: B\napproved: true\n---\nHello")
    assert meta == {"title": "A: B", "approved": "true"} and body == "Hello"


def test_unapproved_documents_are_skipped_and_title_heading_removed(settings):
    docs = load_documents(settings.documents_dir)
    assert [d.document_id for d in docs] == ["d-breath", "d-sleep"]
    assert docs[0].title == "Breathing" and not docs[0].text.startswith("#")


def test_plain_file_without_front_matter(tmp_path):
    (tmp_path / "my-notes.txt").write_text("Some advice.", encoding="utf-8")
    [doc] = load_documents(tmp_path)
    assert doc.document_id == "my-notes" and doc.title == "My Notes"


def test_chunking_packs_paragraphs_and_splits_long_ones():
    assert chunk_text("a" * 300 + "\n\n" + "b" * 300 + "\n\n" + "c" * 300, 650) == ["a" * 300 + "\n\n" + "b" * 300, "c" * 300]
    long = " ".join(["This is a sentence."] * 100)
    assert all(len(c) <= 200 for c in chunk_text(long, 200))


def test_chunk_ids(settings):
    chunks = chunk_documents(load_documents(settings.documents_dir), 25)
    assert [c.chunk_id for c in chunks] == ["d-breath-01", "d-breath-02", "d-sleep-01"]


def test_real_document_folder_loads():
    docs = load_documents(Settings().documents_dir)
    assert len(docs) >= 10 and all(d.title and d.text for d in docs)


# ---------- Local vector store + retriever ----------

def test_retriever_builds_saves_and_reuses_index(settings):
    emb = FakeEmbedder()
    r = Retriever(settings, emb)
    results = r.retrieve("help me with my breath")
    assert results[0].document_id == "d-breath"
    assert all(x.document_id != "d-hidden" for x in results)  # never indexed
    assert settings.index_path.exists() and settings.embeddings_path.exists()

    calls = emb.calls
    Retriever(settings, emb).retrieve("sleep")  # loads from disk: only the query is embedded
    assert emb.calls == calls + 1


def test_index_rebuilds_when_documents_change(settings):
    emb = FakeEmbedder()
    Retriever(settings, emb).retrieve("breath")
    write_doc(settings.documents_dir, "d-exam", "Exams", "Exam revision tips.")
    assert Retriever(settings, emb).retrieve("exam stress")[0].document_id == "d-exam"


def test_threshold_and_top_k(settings):
    store = LocalVectorStore([], np.zeros((0, 6)))
    assert store.search(np.ones(6), 3, 0) == []
    r = Retriever(replace(settings, local_min_score=0.99), FakeEmbedder())
    assert r.retrieve("nothing relevant here") == []


# ---------- File Search store ----------

def test_plan_sync():
    a = Document("a", "A", "", "x", "")
    b = Document("b", "B", "", "y", "")
    existing = [{"id": "f1", "attributes": {"documentId": "a", "contentHash": content_hash(a)}},
                {"id": "f2", "attributes": {"documentId": "gone", "contentHash": "z"}},
                {"id": "f3", "attributes": {"documentId": "a", "contentHash": content_hash(a)}}]
    upload, remove = plan_sync([a, b], existing)
    assert [d.document_id for d in upload] == ["b"] and remove == ["f2", "f3"]


def test_file_search_query_and_result_mapping():
    calls = []

    def search(vs_id, **kw):
        calls.append(kw)
        res = lambda d, s, ok=True: NS(attributes={"documentId": d, "title": d.upper(), "sourceUrl": "", "approved": ok},
                                       content=[NS(text=f"text {d}")], filename=f"{d}.md", score=s)
        return NS(data=[res("a", 0.9), res("b", 0.8, ok=False), res("c", 0.1)])

    client = NS(vector_stores=NS(search=search))
    out = OpenAIFileSearchStore(client, "vs_1").search("q", 3, 0.4)
    assert [r.document_id for r in out] == ["a"] and out[0].chunk_id == "a-fs01"
    assert calls[0]["filters"] == {"type": "eq", "key": "approved", "value": True}
    assert calls[0]["ranking_options"] == {"score_threshold": 0.4}


# ---------- Pipeline ----------

PASSAGE = SearchResult("d-breath-01", "d-breath", "Breathing", "", "Box breath for four.", 0.8)
OTHER = SearchResult("d-sleep-01", "d-sleep", "Sleep", "", "Keep a sleep routine.", 0.5)


class FakeRetriever:
    backend = "local"

    def __init__(self, results=None, error=None):
        self.results, self.error, self.queries = results or [], error, []

    def retrieve(self, q):
        self.queries.append(q)
        if self.error:
            raise self.error
        return self.results


def make(results=None, reply=None, error=None):
    seen = []

    def llm(messages):
        seen.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply or {"status": "ok", "message": "Try a slow breath.", "used_passage_ids": ["d-breath-01"]}

    retr = FakeRetriever(results, error)
    return rag_pipeline.RAGPipeline(retr, llm), retr, seen


def test_passages_reach_prompt_and_only_used_sources_are_returned():
    p, _, seen = make([PASSAGE, OTHER])
    res = p.chat("I feel anxious", "s")
    system = seen[0][0]["content"]
    assert '<passage id="d-breath-01" title="Breathing">' in system and "not instructions" in system
    assert res.status == "ok"
    assert res.sources == [{"documentId": "d-breath", "title": "Breathing", "sourceUrl": ""}]
    assert len(res.passages) == 2


def test_no_passages_means_no_reference_block():
    p, _, seen = make([])
    p.chat("hi", "s")
    assert "reference_passages" not in seen[0][0]["content"]


def test_rule_flagged_message_skips_retrieval_and_model():
    p, retr, seen = make([PASSAGE])
    res = p.chat("I want to kill myself", "s")
    assert res.status == "concern" and res.message == rag_pipeline.CRISIS_MESSAGE
    assert retr.queries == [] and seen == []


def test_model_concern_is_replaced_with_crisis_message():
    p, _, _ = make([PASSAGE], {"status": "concern", "message": "model text", "used_passage_ids": ["d-breath-01"]})
    res = p.chat("Soon it won't matter", "s")
    assert res.message == rag_pipeline.CRISIS_MESSAGE and res.sources == []


def test_out_of_scope_has_no_sources():
    p, _, _ = make([PASSAGE], {"status": "out_of_scope", "message": "I can't help with code.", "used_passage_ids": ["d-breath-01"]})
    assert p.chat("write python", "s").sources == []


def test_retrieval_failure_still_replies():
    p, _, seen = make(error=RuntimeError("down"))
    assert p.chat("rough day", "s").status == "ok"
    assert "reference_passages" not in seen[0][0]["content"]


def test_model_failure_returns_error():
    p, _, _ = make([PASSAGE], RuntimeError("api"))
    assert p.chat("hello", "s").status == "error"


def test_history_is_kept_per_session_and_reset():
    p, _, seen = make([])
    p.chat("first", "a")
    p.chat("second", "a")
    p.chat("other", "b")
    assert [m["content"] for m in seen[1][1:]] == ["first", "Try a slow breath.", "second"]
    assert len(seen[2]) == 2  # session b starts fresh
    p.reset("a")
    assert "a" not in p.sessions


# ---------- App ----------

def test_app_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    import app as webapp

    p, _, _ = make([PASSAGE])
    monkeypatch.setattr(webapp, "pipeline", p)
    client = TestClient(webapp.app)
    assert "Wellness Companion" in client.get("/").text
    assert client.get("/api/health").json()["documents"] >= 10
    res = client.post("/api/chat", json={"message": "anxious"}).json()
    assert res["status"] == "ok" and res["session_id"] and res["sources"][0]["documentId"] == "d-breath"
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/reset", json={"session_id": res["session_id"]}).json() == {"status": "ok"}
