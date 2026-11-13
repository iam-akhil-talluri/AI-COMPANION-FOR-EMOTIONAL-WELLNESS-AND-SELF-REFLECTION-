# RAG Implementation: Emotional Wellness Companion

A retrieval-augmented generation (RAG) chat app. It answers using **approved wellness resources** and keeps the companion's safety rules in place. It uses the OpenAI API for embeddings and chat, and supports two retrieval backends:

| `VECTOR_BACKEND` | How passages are found |
|---|---|
| `local` (default) | OpenAI embeddings are stored in `embeddings/` and `vector_db/`, and search is cosine similarity |
| `openai_file_search` | A hosted OpenAI vector store (File Search), searched with `vector_stores.search` |

## Setup

```powershell
cd RAG-Implementation
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env         # then put your OPENAI_API_KEY in .env
```

`.env` is git-ignored. The key is only read on the server and is never sent to the browser.

## Run the app

```powershell
python -m src.retriever --rebuild                              # build the local index (also happens on the first chat)
python -m src.retriever --backend openai_file_search --rebuild # optional: create and sync the OpenAI vector store
uvicorn app:app --reload --port 8001
```

Open **http://localhost:8001**. Each reply shows the resources it drew on. "Retrieved passages" shows everything retrieval returned, with scores, and marks which documents were used.

To use File Search, set `VECTOR_BACKEND=openai_file_search` in `.env` and restart.

## Project structure

```
data/wellness_documents/   approved resources (.md / .txt / .pdf), one per document
embeddings/                embeddings.npy: chunk vectors (generated)
vector_db/                 index.json: chunk metadata; file_search_store.json: vector store id (generated)
src/
  config.py                settings from .env
  document_loader.py       load documents, read front matter, skip approved: false
  chunking.py              paragraph-based chunks (max 800 chars)
  embedding.py             OpenAI embeddings, normalised
  vector_store.py          LocalVectorStore and OpenAIFileSearchStore (same search interface)
  retriever.py             picks the backend, auto-rebuilds the local index when documents change
  rag_pipeline.py          safety rules -> retrieve -> prompt -> OpenAI chat -> reply + sources
app.py                     FastAPI server: /, /api/chat, /api/health, /api/documents, /api/reset, /api/reindex
static/index.html          chat UI
tests/test_rag.py          offline tests (no API key needed)
```

## How a message is handled

1. **Safety rules.** Messages matching crisis patterns get predefined crisis resources. Retrieval and the model are skipped.
2. **Retrieve.** The top `TOP_K` passages scoring at least the backend's threshold (`LOCAL_MIN_SCORE=0.22`, `FILE_SEARCH_MIN_SCORE=0.40`).
3. **Augment.** The passages go into the system prompt as reference information, not instructions. The model is told to describe techniques as written and not merge them.
4. **Generate.** OpenAI chat with a strict JSON schema: `{status, message, used_passage_ids}`.
5. **Respond.** If the status is `concern`, the reply is replaced with crisis resources. If it is `ok`, `sources` lists only the documents in `used_passage_ids`.

If retrieval fails, the companion still replies, just without passages.

## Adding a resource

Add a file to `data/wellness_documents/`:

```markdown
---
documentId: wellness-011
title: Resource title
sourceUrl: https://...
approved: true
---

# Resource title

Paragraphs separated by blank lines.
```

The local index rebuilds itself on the next chat. For File Search, run `python -m src.retriever --backend openai_file_search --rebuild`: it uploads new or changed documents and removes any deleted or set to `approved: false`.

## Command line

```powershell
python -m src.retriever "I can't sleep"                 # show retrieved passages and scores
python -m src.rag_pipeline "I'm stressed about exams"   # one full RAG turn
pytest                                                  # 20 offline tests
```

## Thresholds

The two backends score on different scales. The thresholds come from the evaluation in the team backend (`docs/FILE_SEARCH.md`), using 20 labelled questions and 5 off-topic ones:

- **Local:** off-topic questions scored at most 0.17 and correct documents at least 0.26, so `0.22`.
- **File Search:** off-topic questions scored below 0.01 and correct documents at least 0.54, so `0.40`.
