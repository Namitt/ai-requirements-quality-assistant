from __future__ import annotations

# Deliberately small demo source text, built strictly from the outcomes
# docs/demo-script.md already specifies for the DUPLICATE_NEAR walkthrough:
# one clean requirement (PASS), one vague one (WARN), and a near-identical
# pair (FAIL). All four relate to one retail scenario: store managers
# currently handling staff absence requests by email.
#
# This is realistic *input* to a live AI extraction call, not a scripted
# transcript - extraction is non-deterministic (see limitations.md), so the
# exact wording the model returns can vary between runs. The source text is
# written so the three intended outcomes are the natural reading, not
# guaranteed on every call.

DEMO_TITLE = "Store manager absence-request process (call notes)"

DEMO_SOURCE_TEXT = """\
Notes from a call with the regional retail operations lead, discussing how \
store managers currently handle staff absence requests.

Right now, when someone on the shop floor wants to book time off, they \
just email their store manager directly, and it's honestly a mess - \
nothing's tracked centrally, so if a manager goes on leave themselves, \
requests can just sit in an inbox for weeks. The regional lead wants a way \
to fix this before the next scheduling cycle.

Whatever we build needs to notify the store manager within 2 hours of an \
absence request being submitted, so nothing gets missed over a weekend.

She also wants managers to be able to review requests in some kind of \
user-friendly way, since some of the current store managers aren't very \
tech-savvy and the last system the company tried was apparently a \
nightmare to use.

On approvals: the system shall allow store managers to approve or reject \
absence requests submitted by their staff. Actually, thinking about it \
more, the system shall allow store managers to approve or decline absence \
requests submitted by their staff - either way, they need the ability to \
make that call themselves, we don't want head office approving on their \
behalf.
"""
