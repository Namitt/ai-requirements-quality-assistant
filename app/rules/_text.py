from __future__ import annotations

import re
import string
from difflib import SequenceMatcher

_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    lowered = text.lower()
    stripped = lowered.translate(_PUNCTUATION_TABLE)
    collapsed = _WHITESPACE_RE.sub(" ", stripped)
    return collapsed.strip()


def similarity(a: str, b: str) -> float:
    norm_a, norm_b = normalize(a), normalize(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()
