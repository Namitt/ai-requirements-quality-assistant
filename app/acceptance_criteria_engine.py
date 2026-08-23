from __future__ import annotations

from sqlalchemy.orm import Session

from app.acceptance_criteria import AcceptanceCriteriaError
from app.acceptance_criteria.parser import parse_response
from app.acceptance_criteria.prompt import ACCEPTANCE_CRITERIA_PROMPT_VERSION, build_prompt
from app.acceptance_criteria_validation_engine import run_acceptance_criteria_validation
from app.extraction.client import ExtractionClient
from app.models import AcceptanceCriterion, ExtractedAcceptanceCriterion, Requirement


class AcceptanceCriteriaReplaySourceNotFoundError(AcceptanceCriteriaError):
    pass


class AcceptanceCriteriaReplaySourceNotLiveError(AcceptanceCriteriaError):
    pass


def draft_acceptance_criteria(
    session: Session,
    client: ExtractionClient,
    requirement_id: int,
) -> AcceptanceCriterion:
    requirement = session.get(Requirement, requirement_id)
    if requirement is None:
        raise ValueError(f"Requirement {requirement_id} does not exist")

    try:
        prompt = build_prompt(requirement.current_text)
        call_result = client.complete(prompt)
        candidate = parse_response(call_result.text)

        extracted = ExtractedAcceptanceCriterion(
            requirement_id=requirement.id,
            criterion_text=candidate.criterion_text,
            mode="live",
            model_name=client.model_name,
            prompt_version=ACCEPTANCE_CRITERIA_PROMPT_VERSION,
        )
        session.add(extracted)
        session.flush()

        acceptance_criterion = AcceptanceCriterion(
            source_extraction_id=extracted.id,
            current_text=extracted.criterion_text,
        )
        session.add(acceptance_criterion)
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(acceptance_criterion)

    # Validation is a separate, independently atomic step -
    # run_acceptance_criteria_validation() owns its own commit/rollback
    # boundary, mirroring how replay mode (Milestone 6) separates the
    # create-transaction from the validate-transaction rather than folding
    # both into one.
    run_acceptance_criteria_validation(session, acceptance_criterion.id)

    session.refresh(acceptance_criterion)
    return acceptance_criterion


def replay_acceptance_criteria(
    session: Session,
    live_extracted_acceptance_criteria_id: int,
) -> AcceptanceCriterion:
    live_extracted = session.get(
        ExtractedAcceptanceCriterion, live_extracted_acceptance_criteria_id
    )
    if live_extracted is None:
        raise AcceptanceCriteriaReplaySourceNotFoundError(
            f"Extracted acceptance criterion {live_extracted_acceptance_criteria_id} "
            "does not exist."
        )
    if live_extracted.mode != "live":
        raise AcceptanceCriteriaReplaySourceNotLiveError(
            "Only a live acceptance criterion draft can be replayed - extracted "
            f"acceptance criterion {live_extracted_acceptance_criteria_id} has "
            f"mode={live_extracted.mode!r}."
        )

    try:
        replay_extracted = ExtractedAcceptanceCriterion(
            requirement_id=live_extracted.requirement_id,
            criterion_text=live_extracted.criterion_text,
            mode="replay",
            replayed_from_id=live_extracted.id,
            model_name=live_extracted.model_name,
            prompt_version=live_extracted.prompt_version,
        )
        session.add(replay_extracted)
        session.flush()

        acceptance_criterion = AcceptanceCriterion(
            source_extraction_id=replay_extracted.id,
            current_text=replay_extracted.criterion_text,
        )
        session.add(acceptance_criterion)
        session.commit()
    except Exception:
        session.rollback()
        raise

    session.refresh(acceptance_criterion)

    run_acceptance_criteria_validation(session, acceptance_criterion.id)

    session.refresh(acceptance_criterion)
    return acceptance_criterion
