from __future__ import annotations

ACCEPTANCE_CRITERIA_PROMPT_VERSION = "1.0.0"

_PROMPT_TEMPLATE = """You are drafting a single Given/When/Then acceptance criterion for one \
software requirement.

Read the requirement below and produce exactly one acceptance criterion that would help \
verify it has been correctly implemented, written in Given/When/Then form.

Respond with ONLY a single JSON object in exactly this shape, and nothing \
else - no markdown code fences, no commentary, no explanation:

{{"criterion_text": "Given ..., when ..., then ..."}}

Requirement:
\"\"\"
{requirement_text}
\"\"\"
"""


def build_prompt(requirement_text: str) -> str:
    return _PROMPT_TEMPLATE.format(requirement_text=requirement_text)
