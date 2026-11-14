"""Rule-based safety screening that runs before any message reaches the model.

The rules are intentionally conservative: a false positive shows the user
support resources, while a false negative could miss someone at risk. The model
also classifies each message (see llm.py) as a second layer.
"""

import re

_CONCERN_PATTERNS = [
    r"\bkill(ing)?\s+my\s*self\b",
    r"\bend(ing)?\s+(my|it)\s+(life|all)\b",
    r"\bsuicid(e|al)\b",
    r"\bwant\s+to\s+die\b",
    r"\bdon'?t\s+want\s+to\s+(live|be\s+alive|exist)\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bself[\s-]?harm(ing)?\b",
    r"\b(cut|cutting|hurt|hurting)\s+my\s*self\b",
    r"\boverdos(e|ing)\b",
    r"\b(kill|hurt)\s+(him|her|them|someone|somebody|people)\b",
    r"\b(being|getting)\s+(abused|hit|beaten)\b",
]

_CONCERN_RE = re.compile("|".join(_CONCERN_PATTERNS), re.IGNORECASE)

# Predefined escalation text. The model never writes this response.
# TODO: have the team review these resources for the deployment region.
ESCALATION_MESSAGE = (
    "It sounds like you may be going through something really serious, and you "
    "deserve support from a person right now. I'm an AI companion and can't "
    "provide crisis care. If you are in immediate danger, please call your local "
    "emergency number. In the US you can call or text 988 (Suicide & Crisis "
    "Lifeline), and findahelpline.com lists free, confidential helplines in "
    "other countries."
)


def screen_message(text: str) -> bool:
    """Return True if the message needs safety escalation."""
    return bool(_CONCERN_RE.search(text))
