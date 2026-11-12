"""Offline tests for the RAG pipeline: embeddings are replaced with fakes."""

import json

import pytest
from fastapi.testclient import TestClient

from app import main, rag, sessions
from app.config import get_settings
from app.llm import build_system_prompt

client = TestClient(main.app)


# ---------- Chunking ----------

def test_chunk_text_splits_on_paragraphs_and_respects_size():
    text = "\n\n".join(["a" * 300, "b" * 300, "c" * 300])
    chunks = rag.chunk_text(text, max_chars=650)
    assert chunks == ["a" * 300 + "\n\n" + "b" * 300, "c" * 300]


def test_only_approved_documents_are_chunked():
    docs = [
        {"documentId": "d1", "title": "Yes", "sourceUrl": "", "approved": True, "text": "One.\n\nTwo."},
        {"documentId": "d2", "title": "No", "sourceUrl": "", "approved": False, "text": "Hidden."},
    ]
    chunks = rag.build_chunks(docs)
    assert {c["documentId"] for c in chunks} == {"d1"}
    assert chunks[0]["chunkId"] == "d1-01"
    assert set(chunks[0]) == {"documentId", "chunkId", "title", "sourceUrl", "text", "approved"}


def test_knowledge_base_file_is_valid():
    data = json.loads(get_settings().knowledge_base_path.read_text(encoding="utf-8"))
    ids = [d["documentId"] for d in data["documents"]]
    assert len(ids) == len(set(ids))
    assert rag.build_chunks(data["documents"])


# ---------- Ranking ----------

def _chunk(cid, emb, approved=True):
    return {"documentId": cid, "chunkId": f"{cid}-01", "title": cid, "sourceUrl": "",
            "text": cid, "approved": approved, "embedding": emb}


def test_rank_chunks_orders_by_similarity_and_applies_threshold():
    chunks = [_chunk("far", [0, 1]), _chunk("near", [1, 0.1]), _chunk("mid", [1, 1])]
    ranked = rag.rank_chunks([1, 0], chunks, top_k=3, min_score=0.5)
    assert [c.document_id for c in ranked] == ["near", "mid"]


def test_rank_chunks_skips_unapproved():
    ranked = rag.rank_chunks([1, 0], [_chunk("x", [1, 0], approved=False)], top_k=3, min_score=0)
    assert ranked == []


# ---------- Prompt augmentation ----------

def test_context_is_added_to_system_prompt_only_when_present():
    assert "reference_passages" not in build_system_prompt("")
    prompt = build_system_prompt("<passage>Box breathing</passage>")
    assert "Box breathing" in prompt
    assert "not instructions" in prompt


# ---------- End to end through /chat ----------

@pytest.fixture
def rag_chat(monkeypatch):
    calls = []
    retrieved = [rag.RetrievedChunk("wellness-001", "wellness-001-02", "Slow Breathing for Stress", "",
                                    "Box breathing: in for four...", 0.71)]

    async def fake_retrieve(query):
        return retrieved

    async def fake_generate_reply(history, user_text, context=""):
        calls.append(context)
        return "ok", "Let's try a slow breath together. How does that feel?"

    monkeypatch.setattr(rag, "retrieve", fake_retrieve)
    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(sessions, "_sessions", {})
    return calls


def test_retrieved_passages_reach_the_model_and_sources_are_returned(rag_chat):
    res = client.post("/chat", json={"message": "I feel anxious", "session_id": "r1"}).json()
    assert "Box breathing" in rag_chat[0]
    assert res["sources"] == [{"documentId": "wellness-001", "title": "Slow Breathing for Stress", "sourceUrl": ""}]


def test_rules_escalation_skips_retrieval(monkeypatch):
    async def must_not_run(query):
        raise AssertionError("retrieval should not run for flagged messages")

    monkeypatch.setattr(rag, "retrieve", must_not_run)
    res = client.post("/chat", json={"message": "I want to kill myself"}).json()
    assert res["status"] == "concern"
    assert res["sources"] == []


def test_retrieval_failure_still_returns_a_reply(monkeypatch):
    async def broken(query):
        raise rag.RetrievalError("embedding API down")

    async def fake_generate_reply(history, user_text, context=""):
        assert context == ""
        return "ok", "I'm here. What's on your mind?"

    monkeypatch.setattr(rag, "retrieve", broken)
    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(sessions, "_sessions", {})
    res = client.post("/chat", json={"message": "Rough day"}).json()
    assert res["status"] == "ok"
    assert res["sources"] == []


# ---------- Index build with fake embeddings ----------

def test_build_index_and_retrieve_with_fake_embeddings(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "rag_index_path", tmp_path / "rag_index.json")
    monkeypatch.setattr(rag, "_index", None)

    def fake_vec(text):
        t = text.lower()
        return [float("breath" in t), float("sleep" in t), 0.01]

    async def fake_embed(texts):
        return [fake_vec(t) for t in texts]

    monkeypatch.setattr(rag, "embed_texts", fake_embed)

    import asyncio
    results = asyncio.run(rag.retrieve("Can you help me with my breathing?"))
    assert results and results[0].document_id == "wellness-001"
    saved = json.loads((tmp_path / "rag_index.json").read_text(encoding="utf-8"))
    assert all("embedding" in c for c in saved["chunks"])
    monkeypatch.setattr(rag, "_index", None)
