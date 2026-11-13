# OpenAI File Search Integration

Owner: Emmanuel · Backend coordination: Akhil · Last updated: 2026-11-13

The companion can now retrieve passages from the approved wellness resources through **OpenAI File Search** (a hosted OpenAI vector store), as an alternative to the local embedding index. The rest of the conversation workflow is unchanged.

## 1. How it fits the existing workflow

```
POST /chat
  ├─ safety rules (app/safety.py) ── flagged → crisis message, no retrieval, no model
  ├─ rag.retrieve(message)
  │     RAG_BACKEND=local               → rag_index.json + cosine similarity (unchanged)
  │     RAG_BACKEND=openai_file_search  → file_search.search() → vector_stores.search
  ├─ rag.format_context(chunks)  → <reference_passages> block in the system prompt (unchanged)
  ├─ llm.generate_reply()        → Chat Completions, strict JSON {status, message} (unchanged)
  └─ model "concern" → crisis message; "ok" → reply + sources (unchanged)
```

**Design choice: the search endpoint, not the Responses API `file_search` tool.** Calling `vector_stores.search` directly returns passages *before* the chat call, so:

- `llm.py` keeps its strict JSON output schema and the two-layer safety classification. Nothing in the prompt or output format changes.
- We decide exactly what reaches the model: only `approved` documents, top-k, above a score threshold.
- Every passage has its `documentId`, title and score, so the frontend `sources` list keeps working.
- If File Search is down, the chat still replies without passages, as with the local index.

The trade-off: the model can't run follow-up searches itself. For short, single-topic wellness messages that isn't needed.

## 2. Changes made

| File | Change |
|---|---|
| `backend/app/file_search.py` | **New.** Vector store sync (upload, replace, remove), search, and a CLI (`sync`, `status`, `query`). |
| `backend/app/eval_retrieval.py` | **New.** Retrieval accuracy and relevance evaluation for both backends. |
| `backend/app/config.py` | New settings: `RAG_BACKEND`, `OPENAI_VECTOR_STORE_ID`, `VECTOR_STORE_STATE_PATH`, `FILE_SEARCH_MIN_SCORE`. |
| `backend/app/rag.py` | `retrieve()` sends the call to `file_search.search()` when `RAG_BACKEND=openai_file_search`. Nothing else changed. |
| `backend/.env.example`, `.gitignore` | New settings documented; `data/vector_store.json` git-ignored. |
| `backend/tests/test_file_search.py` | **New.** 12 offline tests with a fake OpenAI client. |
| `backend/tests/test_file_search_live.py` | **New.** 5 live end-to-end tests of how the model uses retrieved passages. |
| `docs/retrieval_eval.json` | Full evaluation output (every query, rank and score). |

`main.py`, `llm.py`, `safety.py`, `schemas.py` and the frontend are **not** modified.

## 3. Configuration

```env
RAG_BACKEND=openai_file_search     # or "local" (the default)
OPENAI_VECTOR_STORE_ID=            # optional; empty = use the id saved by `sync`
FILE_SEARCH_MIN_SCORE=0.40         # calibrated in section 5
RAG_TOP_K=3                        # shared with the local backend
```

### Vector store

| Item | Value |
|---|---|
| Name | `emotional-wellness-approved-resources` |
| ID | `vs_6af69dc3b4388191bc2fd4f5c554b41b` (saved in `backend/data/vector_store.json`) |
| Contents | 10 approved documents, `wellness-001` … `wellness-010`, one Markdown file each (`# Title` + text) |
| Size | ~16 KB (inside OpenAI's free 1 GB of vector storage) |
| Chunking | OpenAI default (`auto`: 800-token chunks, 400 overlap). Each current document fits in one chunk. |
| File attributes | `documentId`, `title`, `sourceUrl`, `approved: true`, `contentHash` |

The store lives in the OpenAI project of the API key in `backend/.env`. Teammates using a different key or project must run `sync` themselves, or set `OPENAI_VECTOR_STORE_ID` to a store their key can access.

### Search call

```python
client.vector_stores.search(
    vector_store_id,
    query=user_message,
    max_num_results=RAG_TOP_K,
    ranking_options={"score_threshold": FILE_SEARCH_MIN_SCORE},
    filters={"type": "eq", "key": "approved", "value": True},
    rewrite_query=False,      # search the user's own words
)
```

Results without `approved: true` are dropped again in code as a second check, and the threshold is applied again too.

## 4. Operating it

Run from `backend/`:

```bash
python -m app.file_search sync      # create the store if needed; upload new or changed approved docs; remove the rest
python -m app.file_search status    # store status, file counts, document ids
python -m app.file_search query "I can't sleep"   # inspect what one message retrieves
```

`sync` is idempotent: it compares each document's `contentHash` to the stored file. Editing a document re-uploads it and deletes the old file. Removing a document, or setting `approved: false`, deletes its file, so it can no longer be retrieved. **Re-run `sync` after every change to `data/knowledge_base.json`.** Unlike the local index, the vector store does not rebuild itself.

## 5. Testing and results

### Offline (no API key needed): `pytest`

30 passed: 18 existing and 12 new. The new tests cover sync planning (new, changed, un-approved, deleted and duplicate files), the search parameters sent, filtering of unapproved, empty and low-score results, error handling, passages reaching the system prompt through `/chat`, `sources` in the response, and safety-flagged messages never reaching File Search.

### Retrieval accuracy: `python -m app.eval_retrieval`

There are 20 labelled questions, two per document, phrased as a user would say them rather than copied from the documents. There are also 5 off-topic or small-talk questions that should retrieve nothing.

**With no threshold:**

| Backend | Hit@1 | Hit@3 | MRR | Correct doc score (min / mean) | Off-topic top score |
|---|---|---|---|---|---|
| Local (cosine) | 1.00 | 1.00 | 1.00 | 0.26 / 0.43 | ≤ 0.17 |
| File Search | 0.85–0.90 | 1.00 | ≈0.93 | 0.54 / 0.76 | ≤ 0.009 (except "hi": 0.77) |

**With the configured thresholds:**

| Backend | Threshold | Hit@1 | Hit@3 | Off-topic queries retrieving anything |
|---|---|---|---|---|
| Local | 0.30 | 0.90 | 0.90 | 0 / 5 |
| File Search | 0.40 | 0.85 | **1.00** | 1 / 5 ("hi") |

Findings:

- **File Search always gets the correct document into the top 3.** All top 3 passages are given to the model, so Hit@3 is the number that matters most. The 3 top-1 misses are close calls between related documents: sleep vs. grounding for "lying awake with my mind racing", and journaling vs. naming emotions. In every case the expected document was ranked 2nd. Hit@1 varies slightly between runs (0.85–0.90).
- **File Search separates on-topic from off-topic far more clearly.** Off-topic questions score below 0.01 and relevant ones score 0.54 or higher, so the 0.40 threshold leaves a wide margin.
- **Short greetings are the one weak spot.** "hi" scores 0.77 against the breathing document. The model is told to ignore passages that don't fit, so the reply is fine, but `sources` would list that document.
- **The local backend's `RAG_MIN_SCORE=0.30` is slightly too strict.** Both self-compassion questions ("I'm always so hard on myself…") score 0.26–0.28 and get no passages at all. A value around 0.22 would keep them and still exclude every off-topic question (max 0.17).

### How the model uses retrieved passages: `tests/test_file_search_live.py`

All 5 passed, and the existing 7 live behaviour tests also pass with `RAG_BACKEND=openai_file_search`.

| Check | Result |
|---|---|
| Anxiety/breathing question uses the breathing resource | ✅ suggests a counted slow-breathing exercise, stays brief |
| Exam stress uses the study resource, in its own words | ✅ "breaking revision into smaller tasks", "short breaks"; no copied 12-word runs |
| Off-topic request | ✅ `out_of_scope`, no passages given to the model, no sources |
| Indirect risk with passages present | ✅ still `concern`, crisis message, no sources |
| Follow-up question | ✅ answered from conversation history |

What reading the replies showed:

- **Techniques can be blended.** For the breathing question the model said "in for four, hold for four, out for six", which mixes *box breathing* (4-4-4-4) with *extended exhale* (4-6). That is harmless here but not faithful to the resource. Possible fix: add "if you suggest a technique from a passage, describe it as written" to `RAG_INSTRUCTIONS`.
- **`sources` lists everything retrieved, not what was used.** For "What was I just telling you about?" the reply used only the conversation history, but 3 documents were still returned as sources. This happens with the local backend too.

## 6. Items for Akhil (backend)

None of these block the File Search integration. They are suggestions only.

1. **Accurate sources.** Add an optional `used_passage_ids` array to the JSON output schema in `llm.py`, and return only those documents from `main.py`. That fixes both the "hi" case and the follow-up case above.
2. **Faithful techniques.** Consider the one-line `RAG_INSTRUCTIONS` addition from section 5.
3. **Local threshold.** Consider lowering `RAG_MIN_SCORE` from 0.30 to about 0.22 (section 5).
4. **Default backend.** `RAG_BACKEND` stays `local` until the team agrees to switch. Switching is a one-line `.env` change, with no code or frontend changes. Deployment then needs a synced vector store in the deployment key's project.
