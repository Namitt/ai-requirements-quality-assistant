from __future__ import annotations

from typing import NamedTuple, Optional


class RuleOutcome(NamedTuple):
    result: str
    message: str
    recommended_action: Optional[str]


class SiblingText(NamedTuple):
    id: int
    text: str
