# Backend (FastAPI)

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add your OPENAI_API_KEY
python -m app.ingest          # optional: builds the RAG index (otherwise built on first chat)
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## `POST /chat`

Request:

```json
{ "message": "I've been stressed about exams", "session_id": "123" }
```

`session_id` is optional; one is generated and returned if omitted.

Response:

```json
{
  "status": "ok",
  "message": "...",
  "session_id": "123",
  "sources": [{ "documentId": "wellness-001", "title": "Slow Breathing for Stress", "sourceUrl": "" }]
}
```

| status | meaning |
|---|---|
| `ok` | Normal reflective reply |
| `out_of_scope` | Request unrelated to emotional wellness; reply redirects gently |
| `concern` | Safety escalation; `message` is the predefined crisis-resources text |
| `error` | The model call failed; safe to retry |

Safety screening runs in two layers: keyword rules (`app/safety.py`) before the model is called, then the model's own classification. Either one returning `concern` replaces the reply with the predefined escalation message.

Session history is in memory for now and is lost on restart.

## RAG (retrieval-augmented generation)

Replies are grounded in approved wellness resources in `data/knowledge_base.json`.

1. **Ingest** (`app/rag.py`, `python -m app.ingest`): approved documents are split into paragraph chunks and embedded with `OPENAI_EMBEDDING_MODEL`. The vectors go to `data/rag_index.json` (git-ignored). The index rebuilds itself whenever the knowledge base or the embedding model changes.
2. **Retrieve**: each message that passes the safety rules is embedded and compared to every chunk by cosine similarity. The top `RAG_TOP_K` chunks scoring at least `RAG_MIN_SCORE` are kept.
3. **Augment** (`app/llm.py`): the passages are added to the system prompt as reference information. They can't change the safety rules or the classification.
4. **Sources**: for `ok` replies, the documents used come back in `sources`.

If retrieval fails, the companion still replies, just without passages. Messages flagged by the safety rules never reach retrieval or the model.

To add a resource, add a document with `documentId`, `title`, `sourceUrl`, `approved` and `text` (paragraphs separated by blank lines). Only `approved: true` documents are indexed.

## Tests

```powershell
pytest                                   # offline: routing, safety, RAG
$env:RUN_LIVE_TESTS="1"; pytest tests/test_ai_behavior.py -v   # real OpenAI API
```
