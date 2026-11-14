"""Live tests against the real OpenAI API (skipped unless RUN_LIVE_TESTS=1).

PowerShell:  $env:RUN_LIVE_TESTS="1"; pytest tests/test_live.py -v -s
"""

import os
import re

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1")

BREATHING_QUESTIONS = [
    "My heart races and I can't catch my breath when I get anxious. What can I do?",
    "Is there a breathing exercise that helps with panic?",
]


def is_blended(text: str) -> bool:
    """Box breathing's hold step combined with extended exhale's out-for-six."""
    t = text.lower()
    hold = re.search(r"\bhold(ing)?\s+(it\s+|your\s+breath\s+)?(for\s+)?(a\s+count\s+of\s+)?(four|4)\b", t)
    out_six = re.search(r"(out|exhal\w*)[^.]{0,40}(six|6)|(six|6)[^.]{0,25}(out|exhal)", t)
    return bool(hold and out_six)


@pytest.mark.parametrize("backend", ["local", "openai_file_search"])
def test_breathing_techniques_are_not_blended(backend, monkeypatch):
    from src.config import get_settings
    from src.rag_pipeline import RAGPipeline

    monkeypatch.setattr(get_settings(), "vector_backend", backend)
    pipeline = RAGPipeline()
    replies = [pipeline.chat(q, f"{backend}-{i}").message
               for i in range(5) for q in BREATHING_QUESTIONS]
    blended = [r for r in replies if is_blended(r)]
    assert not blended, f"{len(blended)}/{len(replies)} blended:\n" + "\n".join(blended)
