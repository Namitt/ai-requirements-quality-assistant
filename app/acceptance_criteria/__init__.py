from __future__ import annotations

from typing import NamedTuple


class AcceptanceCriteriaError(RuntimeError):
    pass


class AcceptanceCriteriaParseError(AcceptanceCriteriaError):
    pass


class ParsedCriterion(NamedTuple):
    criterion_text: str
