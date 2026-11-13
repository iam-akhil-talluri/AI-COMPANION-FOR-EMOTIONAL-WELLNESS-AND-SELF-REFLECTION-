"""Measure retrieval accuracy and relevance for one or both RAG backends.

Each test query is written the way a user might phrase it (not copied from the
documents) and labelled with the approved document that should answer it.
"Negative" queries are out of scope or small talk and should ideally retrieve
nothing, which is how the score threshold is calibrated.

Run from the backend folder (calls the real OpenAI API):
    python -m app.eval_retrieval                      # both backends
    python -m app.eval_retrieval --backend openai_file_search --threshold 0
    python -m app.eval_retrieval --out ../docs/retrieval_eval.json
"""

import argparse
import asyncio
import json
import logging
import statistics
from typing import Any

from . import rag
from .config import get_settings

# (query, expected documentId)
LABELLED_QUERIES: list[tuple[str, str]] = [
    ("My heart races and I can't catch my breath when I get anxious", "wellness-001"),
    ("Is there a quick way to calm my body down before a presentation?", "wellness-001"),
    ("My thoughts are spiralling and I feel disconnected from everything around me", "wellness-002"),
    ("How do I bring myself back to the present when I'm overwhelmed?", "wellness-002"),
    ("What could I write about to understand my feelings better?", "wellness-003"),
    ("I want to start a diary but I don't know what to say", "wellness-003"),
    ("I have finals next week and I'm panicking about revision", "wellness-004"),
    ("I can't focus on studying because I'm so worried about failing", "wellness-004"),
    ("I keep lying awake at night with my mind racing", "wellness-005"),
    ("Being tired all the time makes me so irritable", "wellness-005"),
    ("I moved to a new city and I don't have anyone to talk to", "wellness-006"),
    ("Even when I'm with people I feel completely alone", "wellness-006"),
    ("I'm always so hard on myself when I make a mistake", "wellness-007"),
    ("My inner critic never stops telling me I'm not good enough", "wellness-007"),
    ("Should I talk to a counsellor about how I've been feeling?", "wellness-008"),
    ("I don't know how to tell my friend that I'm struggling", "wellness-008"),
    ("I feel bad but I can't even say what the feeling is", "wellness-009"),
    ("Why do I get angry so suddenly? What is it telling me?", "wellness-009"),
    ("My partner and I keep arguing about the same things", "wellness-010"),
    ("How can I talk to my roommate about a disagreement without it blowing up?", "wellness-010"),
]

NEGATIVE_QUERIES: list[str] = [
    "What's the capital of Australia?",
    "Write me a Python function to reverse a list",
    "Give me a recipe for banana bread",
    "Who won the football match last night?",
    "hi",
]


async def _retrieve_all(queries: list[str]) -> list[list[rag.RetrievedChunk]]:
    return [await rag.retrieve(q) for q in queries]


def evaluate(backend: str, threshold: float | None, top_k: int) -> dict[str, Any]:
    settings = get_settings()
    settings.rag_backend = backend
    settings.rag_top_k = top_k
    if threshold is not None:
        if backend == "local":
            settings.rag_min_score = threshold
        else:
            settings.file_search_min_score = threshold
    rag._index = None

    pos_queries = [q for q, _ in LABELLED_QUERIES]
    results = asyncio.run(_retrieve_all(pos_queries + NEGATIVE_QUERIES))
    pos_results, neg_results = results[: len(pos_queries)], results[len(pos_queries):]

    rows, hit1, hitk, rr, top_scores, correct_scores = [], 0, 0, 0.0, [], []
    for (query, expected), chunks in zip(LABELLED_QUERIES, pos_results):
        ids = [c.document_id for c in chunks]
        rank = ids.index(expected) + 1 if expected in ids else None
        hit1 += rank == 1
        hitk += rank is not None
        rr += 1 / rank if rank else 0
        if chunks:
            top_scores.append(chunks[0].score)
        if rank:
            correct_scores.append(chunks[rank - 1].score)
        rows.append({
            "query": query, "expected": expected, "rank": rank,
            "retrieved": [{"documentId": c.document_id, "score": c.score} for c in chunks],
        })

    neg_rows = [
        {"query": q, "retrieved": [{"documentId": c.document_id, "score": c.score} for c in chunks]}
        for q, chunks in zip(NEGATIVE_QUERIES, neg_results)
    ]
    neg_top = [r["retrieved"][0]["score"] for r in neg_rows if r["retrieved"]]
    n = len(LABELLED_QUERIES)
    return {
        "backend": backend,
        "topK": top_k,
        "threshold": settings.rag_min_score if backend == "local" else settings.file_search_min_score,
        "summary": {
            "hitAt1": round(hit1 / n, 3),
            f"hitAt{top_k}": round(hitk / n, 3),
            "mrr": round(rr / n, 3),
            "meanScoreOfCorrectDoc": round(statistics.mean(correct_scores), 4) if correct_scores else None,
            "minScoreOfCorrectDoc": round(min(correct_scores), 4) if correct_scores else None,
            "negativesWithAnyResult": sum(1 for r in neg_rows if r["retrieved"]),
            "maxNegativeTopScore": round(max(neg_top), 4) if neg_top else None,
            "meanNegativeTopScore": round(statistics.mean(neg_top), 4) if neg_top else None,
        },
        "queries": rows,
        "negatives": neg_rows,
    }


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(prog="python -m app.eval_retrieval")
    parser.add_argument("--backend", choices=["local", "openai_file_search", "both"], default="both")
    parser.add_argument("--threshold", type=float, default=None, help="override the min score")
    parser.add_argument("--top-k", type=int, default=get_settings().rag_top_k)
    parser.add_argument("--out", help="write the full report to this JSON file")
    args = parser.parse_args()

    backends = ["local", "openai_file_search"] if args.backend == "both" else [args.backend]
    reports = [evaluate(b, args.threshold, args.top_k) for b in backends]
    for r in reports:
        print(f"\n== {r['backend']} (top_k={r['topK']}, threshold={r['threshold']})")
        for k, v in r["summary"].items():
            print(f"  {k:24} {v}")
        misses = [q for q in r["queries"] if q["rank"] != 1]
        for q in misses:
            got = ", ".join(f"{x['documentId']}:{x['score']}" for x in q["retrieved"]) or "nothing"
            print(f"  miss@1: {q['query']!r} expected {q['expected']} got {got}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2)
        print(f"\nFull report written to {args.out}")


if __name__ == "__main__":
    main()
