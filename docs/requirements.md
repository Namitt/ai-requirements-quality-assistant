# Requirements — AI Requirements Quality Assistant

## Purpose

This project demonstrates how a Business Analyst can use AI to accelerate
requirements extraction while keeping deterministic validation and human
judgement as the actual gate for quality. AI drafts; a human and a rule
engine decide what is fit to move into delivery.

## Primary user

A single Business Analyst / Data Analyst, acting as both the author of
source material and the reviewer/approver of extracted requirements.
The system is single-user and local-first; there is no concept of a
second reviewer or approval chain in this version.

## Core user journey

1. The analyst pastes unstructured source text (e.g. meeting notes, an
   email, a stakeholder message) into the application.
2. The analyst runs extraction, either live (calls the AI) or replay
   (reuses a previously captured AI result).
3. The system creates candidate requirements from the AI output and
   automatically pairs each with a reviewable requirement record.
4. The system runs deterministic validation on every requirement and
   shows PASS / WARN / FAIL with an explanation for each.
5. The analyst reviews the results, edits requirement text where
   needed, and re-validates.
6. The analyst approves or rejects each requirement. WARN requires an
   explicit acknowledgement to approve; FAIL blocks approval entirely.
7. The analyst can trace any requirement back to the exact AI output
   and source text it originated from.
8. The analyst can view a summary distinguishing AI-original content,
   human edits, validation outcomes, and approval decisions.

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR1 | The system shall accept raw source text as input. |
| FR2 | The system shall extract candidate requirements from source text using an AI model and automatically create a paired, reviewable requirement record for each candidate. |
| FR3 | The system shall run deterministic validation rules against every requirement automatically after extraction and after any edit. |
| FR4 | The system shall present validation results as PASS, WARN, or FAIL, each with an explanation and a recommended next action. |
| FR5 | The system shall allow the analyst to edit requirement text and shall retain a full edit history. |
| FR6 | The system shall allow the analyst to approve or reject each requirement. |
| FR7 | The system shall require and record an explicit acknowledgement (who, and when) before a WARN requirement can be approved, and shall block approval of any requirement with a FAIL result. Approval alone must never be treated as evidence that a WARN was acknowledged. |
| FR8 | The system shall maintain traceability from every requirement to its originating AI output and to the exact span of source text it was extracted from. |
| FR9 | The system shall support a replay mode that re-runs a previously captured AI extraction through the same validation and review pipeline without making a live API call. |
| FR10 | The system shall provide a summary view showing, per requirement, its `origin` (AI-generated or manual), `validation_state` (PASS/WARN/FAIL), and `review_status` (pending/approved/rejected). |
| FR11 | The system shall invalidate any existing WARN acknowledgement whenever a requirement is revalidated, requiring a fresh acknowledgement before that requirement can be approved again. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR1 | Validation must be deterministic and explainable — every result must state what was checked and why it produced that result. |
| NFR2 | The system must never present PASS as a claim that a requirement is business-correct. |
| NFR3 | The system must remain fully demonstrable without a live network connection or API key, via replay mode. |
| NFR4 | The system is single-user and local-first; no authentication is implemented. |
| NFR5 | AI-original content must remain visually and structurally distinguishable from human-edited content at all times. |

## Out of scope

- **Authentication and multi-user access** — single-analyst workflow;
  adds an authorization model this demonstration does not need.
- **Real-time or multi-party collaboration** — depends on multi-user
  access, which is itself out of scope.
- **Integration with Jira, Azure DevOps, or similar delivery tools** —
  traceability and export beyond this application are not part of the
  requirements-quality story being demonstrated.
- **Model fine-tuning** — extraction is demonstrated with a
  general-purpose model call; fine-tuning is a production concern, not
  a demonstration concern.
- **Cloud deployment** — this is a local, single-user demonstration
  tool, not a hosted service.
- **Enterprise security controls / security hardening** — not
  evaluated for production deployment; see `limitations.md`.
- **Autonomous approval of requirements by AI, or anything implying
  the system approves requirements without human involvement** —
  directly contradicts the project's core AI principle that AI never
  approves requirements; a human decision is always required.
- **A FAIL override/exception workflow** — left out to keep the
  approval gate simple and unambiguous; a deliberate limitation, not
  an oversight.

Further trade-offs and options considered for these exclusions are
recorded in `decisions-log.md` ("MVP scope boundaries").

## Assumptions

- Source text is pasted directly as plain text; no file upload or
  document parsing is included in the MVP.
- The system operates on a single active project/workspace at a time.

---

# Module 2 — Acceptance Criteria Assistant

## Purpose

Module 2 extends the same workflow one step further: an analyst can ask
AI to draft a structured Given/When/Then acceptance criterion for any
existing requirement, have it checked by a separate deterministic rule
set, and review/approve/reject it independently of the requirement
itself. The AI-drafts / deterministic-rules-validate / human-decides
architecture is unchanged — only the artifact being drafted, checked,
and reviewed is new.

## Primary user

The same single Business Analyst / Data Analyst as Module 1, working on
requirements they have already extracted (of any review status).

## Core user journey

1. From an existing requirement, the analyst requests an AI-drafted
   acceptance criterion, either live (calls the AI) or replay (reuses a
   previously captured live draft for that same requirement).
2. The system creates an immutable AI-origin criterion record and
   automatically pairs it with a reviewable acceptance-criteria record.
3. The system runs four deterministic structural checks on the
   criterion and shows PASS / WARN for each.
4. The analyst reviews the result, edits the criterion text where
   needed, and re-validates.
5. The analyst approves or rejects the criterion. WARN requires an
   explicit acknowledgement to approve; a FAIL result (not reachable by
   any v1 rule, but still enforced) would block approval entirely.
6. Approving, rejecting, or editing a criterion never changes the
   parent requirement's own `review_status`.
7. The analyst can trace any criterion back to the requirement it was
   drafted for, that requirement's own extracted evidence, and the
   exact source text span behind it.

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-M2-01 | The system shall allow the analyst to request an AI-drafted acceptance criterion for any existing requirement, using that requirement's current text as input, regardless of the requirement's `review_status`. |
| FR-M2-02 | The system shall store each AI-drafted acceptance criterion as an immutable, traceable record, and shall automatically create a paired, mutable, reviewable record for it. |
| FR-M2-03 | The system shall automatically run deterministic structural validation on every acceptance criterion, immediately after drafting and after any edit, checking for a Given clause, a When clause, a Then clause, and a measurable condition within the Then clause. |
| FR-M2-04 | The system shall present acceptance-criteria validation results using the same PASS/WARN/FAIL vocabulary, explanation, and recommended-action pattern used for requirement validation. |
| FR-M2-05 | The system shall allow the analyst to edit an acceptance criterion's text and shall retain a full edit history. |
| FR-M2-06 | The system shall allow the analyst to approve or reject each acceptance criterion independently of its parent requirement's own `review_status`, and drafting, approving, or rejecting a criterion shall never change the parent requirement's `review_status`. |
| FR-M2-07 | The system shall block approval of any acceptance criterion with a FAIL validation result, and shall require an explicit, separately recorded acknowledgement before approving a WARN result, invalidating any prior acknowledgement whenever the criterion is revalidated. |
| FR-M2-08 | The system shall maintain traceability from every acceptance criterion to the requirement it was drafted for, that requirement's own extracted evidence and source document, and the model/prompt version used to draft it. |
| FR-M2-09 | The system shall support a replay mode for acceptance criteria that reproduces a previously captured live draft through the same validation and review pipeline without making a live API call, scoped to live drafts belonging to the same requirement, and shall never allow a replay to itself be replayed. |

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-M2-1 | Acceptance-criteria validation must be deterministic and explainable, on the same terms as NFR1. |
| NFR-M2-2 | A PASS structural result must never be presented as a claim that the criterion is business-correct or QA-ready, on the same terms as NFR2. |
| NFR-M2-3 | AI-drafted criterion text must remain visually and structurally distinguishable from analyst-edited text, on the same terms as NFR5. |

## Out of scope

- **UAT test-case generation, automated test execution, or test-runner
  integration** — Module 2 produces reviewable acceptance-criteria
  text only, not executable tests.
- **Integration with Jira, Azure DevOps, or similar delivery tools** —
  same reasoning as Module 1's equivalent exclusion.
- **User-story generation or INVEST checking** — a different artifact
  type from acceptance criteria; not part of this module.
- **Document revision or change-impact analysis, or cross-document
  traceability** — Module 2's traceability chain stays within a single
  requirement and its own source document.
- **Graph visualisation of any kind.**
- **Authentication, multi-user support, or cloud deployment** — same
  reasoning as Module 1's equivalent exclusions.
- **Semantic correctness judgement of a criterion** — structural checks
  only; see the severity framework in `validation-rules.md`.
- **Automatic approval of an acceptance criterion, or automatic
  modification of the parent requirement as a side effect of any
  acceptance-criteria action** — directly contradicts the project's
  core AI principle, extended to this module.

Further reasoning for these exclusions is recorded in
`decisions-log.md`.

## Assumptions

- Every acceptance criterion is AI-origin; there is no manually-authored
  acceptance criterion concept in this version (unlike requirements,
  which support `origin='manual'`).
- A requirement may have any number of acceptance criteria, including
  zero.
