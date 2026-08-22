from __future__ import annotations

from app.rules import SiblingText
from app.rules import ambiguous_wording, duplicate_near, missing_acceptance_condition
from app.rules import missing_actor, possible_contradiction
from app.rules._text import normalize, similarity

# ---------------------------------------------------------------------------
# _text.normalize / _text.similarity
# ---------------------------------------------------------------------------


def test_normalize_lowercases_strips_punctuation_and_collapses_whitespace():
    assert normalize("  Hello,   World!  ") == "hello world"


def test_normalize_trims_surrounding_whitespace():
    assert normalize("   pad me   ") == "pad me"


def test_similarity_is_symmetric():
    a = "The system shall lock a user account after 5 failed login attempts."
    b = "The system shall lock a user account after 3 failed login attempts."
    assert similarity(a, b) == similarity(b, a)


def test_similarity_empty_string_never_matches():
    assert similarity("", "The system shall do something useful.") == 0.0


def test_similarity_whitespace_only_never_matches():
    assert similarity("   ", "The system shall do something useful.") == 0.0


def test_similarity_both_empty_does_not_return_perfect_match():
    assert similarity("", "") == 0.0


# ---------------------------------------------------------------------------
# AMBIGUOUS_WORDING
# ---------------------------------------------------------------------------


def test_ambiguous_wording_pass_example_from_docs():
    text = (
        "The system shall lock a user account after 5 consecutive failed "
        "login attempts within 10 minutes."
    )
    outcome = ambiguous_wording.evaluate(text)
    assert outcome.result == "pass"


def test_ambiguous_wording_warn_example_from_docs():
    text = "The system shall provide a user-friendly interface for account management."
    outcome = ambiguous_wording.evaluate(text)
    assert outcome.result == "warn"
    assert "user-friendly" in outcome.message


def test_ambiguous_wording_is_case_insensitive():
    outcome = ambiguous_wording.evaluate("The response time must be FAST.")
    assert outcome.result == "warn"


# ---------------------------------------------------------------------------
# MISSING_ACCEPTANCE_CONDITION
# ---------------------------------------------------------------------------


def test_missing_acceptance_condition_pass_example_from_docs():
    text = "The page shall load within 2 seconds for 95% of requests under normal load."
    outcome = missing_acceptance_condition.evaluate(text)
    assert outcome.result == "pass"


def test_missing_acceptance_condition_warn_example_from_docs():
    text = "The system shall provide reporting capabilities for administrators."
    outcome = missing_acceptance_condition.evaluate(text)
    assert outcome.result == "warn"


def test_missing_acceptance_condition_conditional_connector_counts_as_signal():
    text = "If the upload fails, the system shall retry the operation."
    outcome = missing_acceptance_condition.evaluate(text)
    assert outcome.result == "pass"


# ---------------------------------------------------------------------------
# MISSING_ACTOR
# ---------------------------------------------------------------------------


def test_missing_actor_pass_example_from_docs():
    text = "The system shall validate the uploaded file format before accepting it."
    outcome = missing_actor.evaluate(text)
    assert outcome.result == "pass"


def test_missing_actor_warn_example_from_docs():
    text = "The uploaded file shall be validated before acceptance."
    outcome = missing_actor.evaluate(text)
    assert outcome.result == "warn"


# ---------------------------------------------------------------------------
# DUPLICATE_NEAR — severity classification boundaries
# ---------------------------------------------------------------------------


def test_duplicate_near_severity_boundary_at_0_70_inclusive():
    assert duplicate_near._severity_for_score(0.70) == "warn"


def test_duplicate_near_severity_just_below_0_70_is_pass():
    assert duplicate_near._severity_for_score(0.6999999) is None


def test_duplicate_near_severity_boundary_at_0_90_inclusive():
    assert duplicate_near._severity_for_score(0.90) == "fail"


def test_duplicate_near_severity_just_below_0_90_is_warn():
    assert duplicate_near._severity_for_score(0.8999999) == "warn"


# ---------------------------------------------------------------------------
# DUPLICATE_NEAR — evaluate()
#
# docs/validation-rules.md's PASS/WARN/FAIL examples were corrected to match
# measured difflib.SequenceMatcher.ratio() scores after an initial mismatch
# was found during implementation. The pairs below were constructed and
# verified independently, before that doc correction, and are kept as-is
# since they already exercise the WARN/FAIL boundary correctly and reliably.
# ---------------------------------------------------------------------------


def test_duplicate_near_pass_example_from_docs():
    text = "The system shall export reports as CSV."
    siblings = [SiblingText(id=1, text="The system shall lock accounts after 5 failed logins.")]
    outcome = duplicate_near.evaluate(text, siblings)
    assert outcome.result == "pass"


def test_duplicate_near_warn_tier_synthetic_pair():
    text = "The system shall send a confirmation email after registration."
    siblings = [
        SiblingText(
            id=2,
            text="The system shall send a confirmation notice after a user registers online.",
        )
    ]
    outcome = duplicate_near.evaluate(text, siblings)
    assert outcome.result == "warn"
    assert "#2" in outcome.message


def test_duplicate_near_fail_tier_synthetic_pair():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [
        SiblingText(
            id=3,
            text="The system shall lock a user account after 5 failed login attempt.",
        )
    ]
    outcome = duplicate_near.evaluate(text, siblings)
    assert outcome.result == "fail"
    assert "#3" in outcome.message


def test_duplicate_near_no_siblings_is_pass():
    outcome = duplicate_near.evaluate("Anything.", [])
    assert outcome.result == "pass"


def test_duplicate_near_empty_text_never_matches_empty_sibling():
    outcome = duplicate_near.evaluate("", [SiblingText(id=1, text="")])
    assert outcome.result == "pass"


def test_duplicate_near_whitespace_only_never_matches():
    outcome = duplicate_near.evaluate("   ", [SiblingText(id=1, text="\t\n")])
    assert outcome.result == "pass"


def test_duplicate_near_selects_worst_severity_among_siblings():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [
        SiblingText(id=1, text="Reports shall be exportable as CSV files."),  # low
        SiblingText(
            id=2,
            text="The system shall send a confirmation notice after a user registers online.",
        ),  # unrelated, low
        SiblingText(
            id=3, text="The system shall lock a user account after 5 failed login attempt."
        ),  # FAIL tier
    ]
    outcome = duplicate_near.evaluate(text, siblings)
    assert outcome.result == "fail"
    assert "#3" in outcome.message


def test_duplicate_near_tie_break_prefers_lower_id():
    text = "The system shall lock a user account after 5 failed login attempts."
    twin_text = "The system shall lock a user account after 5 failed login attempt."
    siblings = [
        SiblingText(id=20, text=twin_text),
        SiblingText(id=10, text=twin_text),
    ]
    outcome = duplicate_near.evaluate(text, siblings)
    assert outcome.result == "fail"
    assert "#10" in outcome.message


# ---------------------------------------------------------------------------
# POSSIBLE_CONTRADICTION
# ---------------------------------------------------------------------------


def test_possible_contradiction_warn_example_from_docs_numeric_case():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [
        SiblingText(
            id=1, text="The system shall lock a user account after 3 failed login attempts."
        )
    ]
    outcome = possible_contradiction.evaluate(text, siblings)
    assert outcome.result == "warn"
    assert "#1" in outcome.message


def test_possible_contradiction_never_fails():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [
        SiblingText(
            id=1, text="The system shall lock a user account after 3 failed login attempts."
        )
    ]
    outcome = possible_contradiction.evaluate(text, siblings)
    assert outcome.result in ("pass", "warn")


def test_possible_contradiction_negation_mismatch():
    text = "The system shall allow administrators to delete a requirement."
    siblings = [
        SiblingText(
            id=2, text="The system shall not allow administrators to delete a requirement."
        )
    ]
    outcome = possible_contradiction.evaluate(text, siblings)
    assert outcome.result == "warn"


def test_possible_contradiction_below_threshold_never_flagged_even_with_differing_numbers():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [SiblingText(id=1, text="Reports shall be exportable within 3 seconds.")]
    outcome = possible_contradiction.evaluate(text, siblings)
    assert outcome.result == "pass"


def test_possible_contradiction_no_siblings_is_pass():
    outcome = possible_contradiction.evaluate("Anything.", [])
    assert outcome.result == "pass"


def test_possible_contradiction_tie_break_prefers_lower_id():
    text = "The system shall lock a user account after 5 failed login attempts."
    siblings = [
        SiblingText(
            id=20, text="The system shall lock a user account after 3 failed login attempts."
        ),
        SiblingText(
            id=10, text="The system shall lock a user account after 3 failed login attempts."
        ),
    ]
    outcome = possible_contradiction.evaluate(text, siblings)
    assert "#10" in outcome.message
