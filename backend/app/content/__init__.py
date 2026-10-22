"""Reviewed, static content: the system prompt, safety templates and support resources.

The wording lives in Markdown and JSON so reviewers can change it without touching Python.
Files are read once per process; restart the server after editing them.
"""

import copy
import json
from functools import lru_cache
from pathlib import Path

CONTENT_DIR = Path(__file__).parent

# Must match the reference in system_prompt.md. If it appears in an AI reply, the
# reply is leaking the system prompt and is blocked by the output check.
POLICY_CANARY = "companion-policy-7f3a"

RESOURCE_KINDS = ("crisis", "abuse", "support")


def _load_json(name: str) -> dict:
    with open(CONTENT_DIR / name, encoding="utf-8") as handle:
        data = json.load(handle)
    data.pop("_note", None)
    return data


@lru_cache
def system_prompt() -> str:
    return (CONTENT_DIR / "system_prompt.md").read_text(encoding="utf-8").strip()


@lru_cache
def _templates() -> dict[str, str]:
    return _load_json("safety_templates.json")


@lru_cache
def _resources() -> dict:
    return _load_json("crisis_resources.json")


def template(name: str) -> str:
    """A reviewed, fixed message. Raises KeyError for an unknown name (a programming error)."""
    return _templates()[name]


def template_names() -> set[str]:
    return set(_templates())


def resources_for(kind: str) -> list[dict]:
    """The support resources for `kind` (crisis | abuse | support), as fresh copies."""
    data = _resources()
    return [dict(copy.deepcopy(data["resources"][key]), id=key) for key in data["sets"][kind]]
