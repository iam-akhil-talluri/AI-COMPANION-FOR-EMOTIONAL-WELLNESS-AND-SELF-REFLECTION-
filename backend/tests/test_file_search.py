"""Offline tests for OpenAI File Search retrieval: the OpenAI client is faked."""

import asyncio
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app import file_search, main, rag, sessions
from app.config import get_settings

client = TestClient(main.app)

DOC = {"documentId": "wellness-001", "title": "Slow Breathing for Stress", "sourceUrl": "https://example.org/b",
       "approved": True, "text": "Box breathing.\n\nExtended exhale."}


def result(doc_id, score, text="Box breathing: in for four...", approved=True, title="Slow Breathing for Stress"):
    attrs = {"documentId": doc_id, "title": title, "sourceUrl": "", "approved": approved}
    return NS(attributes=attrs, content=[NS(text=text, type="text")], file_id=f"file-{doc_id}",
              filename=f"{doc_id}.md", score=score)


class FakeVectorStores:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def search(self, vector_store_id, **kwargs):
        self.calls.append({"vector_store_id": vector_store_id, **kwargs})
        return NS(data=self.results)


@pytest.fixture
def fs(monkeypatch):
    """File Search backend selected, with a fake client and a fixed store id."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rag_backend", "openai_file_search")
    monkeypatch.setattr(settings, "openai_vector_store_id", "vs_test")
    monkeypatch.setattr(settings, "file_search_min_score", 0.0)
    monkeypatch.setattr(settings, "rag_top_k", 3)
    stores = FakeVectorStores([])
    monkeypatch.setattr(file_search, "get_client", lambda: NS(vector_stores=stores))
    return stores


# ---------- Sync planning ----------

def test_plan_sync_uploads_new_and_keeps_unchanged():
    other = {**DOC, "documentId": "wellness-002", "title": "Grounding"}
    existing = [{"id": "f1", "attributes": {"documentId": "wellness-001", "contentHash": file_search.content_hash(DOC)}}]
    upload, remove = file_search.plan_sync([DOC, other], existing)
    assert [d["documentId"] for d in upload] == ["wellness-002"]
    assert remove == []


def test_plan_sync_replaces_changed_and_removes_unapproved_or_deleted():
    edited = {**DOC, "text": "New wording."}
    hidden = {**DOC, "documentId": "wellness-002", "approved": False}
    existing = [
        {"id": "f1", "attributes": {"documentId": "wellness-001", "contentHash": file_search.content_hash(DOC)}},
        {"id": "f2", "attributes": {"documentId": "wellness-002", "contentHash": "x"}},
        {"id": "f3", "attributes": {"documentId": "gone", "contentHash": "y"}},
        {"id": "f4", "attributes": {}},
    ]
    upload, remove = file_search.plan_sync([edited, hidden], existing)
    assert [d["documentId"] for d in upload] == ["wellness-001"]
    assert sorted(remove) == ["f1", "f2", "f3", "f4"]


def test_plan_sync_removes_duplicate_uploads():
    h = file_search.content_hash(DOC)
    existing = [{"id": "a", "attributes": {"documentId": "wellness-001", "contentHash": h}},
                {"id": "b", "attributes": {"documentId": "wellness-001", "contentHash": h}}]
    upload, remove = file_search.plan_sync([DOC], existing)
    assert upload == [] and remove == ["b"]


def test_document_file_and_attributes():
    name, data = file_search.document_file(DOC)
    assert name == "wellness-001.md"
    assert data.decode().startswith("# Slow Breathing for Stress\n\nBox breathing.")
    attrs = file_search.document_attributes(DOC)
    assert attrs["approved"] is True and attrs["sourceUrl"] == "https://example.org/b"


# ---------- Search ----------

def test_search_sends_filter_threshold_and_top_k(fs):
    fs.results = [result("wellness-001", 0.8)]
    chunks = asyncio.run(rag.retrieve("I can't breathe when I'm anxious"))
    call = fs.calls[0]
    assert call["vector_store_id"] == "vs_test"
    assert call["filters"] == {"type": "eq", "key": "approved", "value": True}
    assert call["max_num_results"] == 3
    assert call["ranking_options"] == {"score_threshold": 0.0}
    assert call["rewrite_query"] is False
    assert chunks[0].document_id == "wellness-001"
    assert chunks[0].chunk_id == "wellness-001-fs01"
    assert chunks[0].score == 0.8


def test_search_drops_unapproved_empty_and_low_score_results(fs, monkeypatch):
    monkeypatch.setattr(get_settings(), "file_search_min_score", 0.5)
    fs.results = [result("a", 0.9, approved=False), result("b", 0.9, text="  "),
                  result("c", 0.7), result("d", 0.3)]
    chunks = asyncio.run(rag.retrieve("q"))
    assert [c.document_id for c in chunks] == ["c"]


def test_search_api_failure_is_a_retrieval_error(fs):
    async def boom(*a, **k):
        raise RuntimeError("503")
    fs.search = boom
    with pytest.raises(rag.RetrievalError):
        asyncio.run(rag.retrieve("q"))


def test_missing_vector_store_is_a_retrieval_error(fs, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "openai_vector_store_id", "")
    monkeypatch.setattr(get_settings(), "vector_store_state_path", tmp_path / "none.json")
    with pytest.raises(rag.RetrievalError):
        asyncio.run(rag.retrieve("q"))


def test_saved_state_is_used_when_env_id_is_empty(fs, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "openai_vector_store_id", "")
    monkeypatch.setattr(get_settings(), "vector_store_state_path", tmp_path / "vs.json")
    file_search._write_state({"vectorStoreId": "vs_saved"})
    asyncio.run(rag.retrieve("q"))
    assert fs.calls[0]["vector_store_id"] == "vs_saved"


# ---------- Through /chat: passages reach the model, sources reach the frontend ----------

def test_file_search_passages_flow_through_chat(fs, monkeypatch):
    fs.results = [result("wellness-001", 0.82, text="Box breathing: in for four, hold for four.")]
    contexts = []

    async def fake_generate_reply(history, user_text, context=""):
        contexts.append(context)
        return "ok", "Want to try a slow breath together?"

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(sessions, "_sessions", {})
    res = client.post("/chat", json={"message": "I feel panicky", "session_id": "fs1"}).json()
    assert '<passage id="wellness-001-fs01" title="Slow Breathing for Stress">' in contexts[0]
    assert "Box breathing" in contexts[0]
    assert res["sources"] == [{"documentId": "wellness-001", "title": "Slow Breathing for Stress", "sourceUrl": ""}]


def test_file_search_outage_still_returns_a_reply(fs, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("timeout")
    fs.search = boom

    async def fake_generate_reply(history, user_text, context=""):
        assert context == ""
        return "ok", "I'm here."

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(sessions, "_sessions", {})
    res = client.post("/chat", json={"message": "Rough day"}).json()
    assert res["status"] == "ok" and res["sources"] == []


def test_rules_escalation_skips_file_search(fs):
    res = client.post("/chat", json={"message": "I want to kill myself"}).json()
    assert res["status"] == "concern"
    assert fs.calls == []
