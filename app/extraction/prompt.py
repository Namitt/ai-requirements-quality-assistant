from __future__ import annotations

EXTRACTION_PROMPT_VERSION = "1.0.0"

_PROMPT_TEMPLATE = """You are extracting candidate software requirements from \
unstructured source text (e.g. meeting notes, emails, stakeholder messages).

Read the source text below and identify every distinct candidate requirement \
it implies - a statement of something the system should do.

For each candidate requirement, produce:
- "requirement_text": a single, clearly worded requirement statement (e.g. \
"The system shall ...").
- "source_quote": an exact, contiguous, verbatim excerpt copied \
character-for-character from the source text below that motivates this \
requirement. Do not paraphrase, summarize, or alter this excerpt in any way \
- it must be found exactly as written in the source text.

Respond with ONLY a single JSON object in exactly this shape, and nothing \
else - no markdown code fences, no commentary, no explanation:

{{"requirements": [{{"requirement_text": "...", "source_quote": "..."}}]}}

If the source text contains no identifiable requirements, respond with:

{{"requirements": []}}

Source text:
\"\"\"
{source_text}
\"\"\"
"""


def build_prompt(raw_text: str) -> str:
    return _PROMPT_TEMPLATE.format(source_text=raw_text)
