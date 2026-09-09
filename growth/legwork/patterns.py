"""patterns — what each kind of hand-work actually turns into.

This is the library the whole app hangs off. An owner describes a step and says
what *happens to the information* in it; each of those answers maps to a pattern
here, and a pattern knows four things:

  * what the automated version looks like, in the owner's language
  * how much of that step's hand-time it takes away, **as a range**
  * what it costs to build (effort) and what could go wrong (risk)
  * what it needs from them before it could be built at all

Three rules this file exists to hold:

**Every saving is a range, never a number.** `05` §8 forbids a single-point
figure anywhere a client can see it, and this is the file where one would be
born. `savings_of()` refuses a pattern whose low and high are equal, so a
single point cannot be typed in by accident later.

**One pattern saves almost nothing, on purpose.** `judgement` is the step where
a person decides something, and the honest answer is that it stays with the
person. An owner who hears "all of it can be automated" stops believing the
rest of the sheet. The one pattern that says *no* is what makes the other seven
credible in the room.

**The ranges are wide and each one says why.** A narrow range is a promise, and
nothing here has been measured in a real client's office yet. When the first
three assessments are done, tighten these against what actually happened -- and
change the `why` line at the same time, because it is the range's evidence.
"""

from __future__ import annotations

__all__ = ["HANDLING", "PATTERNS", "handling_choices", "pattern_for",
           "patterns_for_step", "savings_of", "SavingsError"]


class SavingsError(ValueError):
    """A pattern tried to describe a saving as a single number."""


# --------------------------------------------------------------- the answers
#
# What an owner is actually asked about a step. Deliberately phrased as things
# that happen to *the information*, not as software categories -- "it gets typed
# in again" is a sentence an owner says out loud; "data re-entry between systems
# of record" is a sentence a consultant says.

HANDLING = [
    {
        "key": "retyped",
        "label": "Somebody types it in again somewhere else",
        "hint": "It exists in one place and gets keyed into a second.",
    },
    {
        "key": "looked-up",
        "label": "Somebody has to go and find something",
        "hint": "Hunting through email, a folder, a binder, or asking around.",
    },
    {
        "key": "written",
        "label": "The same document or email gets written again",
        "hint": "A quote, a work order, a follow-up — written from scratch each time.",
    },
    {
        "key": "chased",
        "label": "Somebody has to chase a person",
        "hint": "Ringing, re-sending, asking again. Waiting is not the work; the chasing is.",
    },
    {
        "key": "paper",
        "label": "It's on paper, a whiteboard, or a text message",
        "hint": "It gets written down once and typed up later, or it gets lost.",
    },
    {
        "key": "checked",
        "label": "Somebody checks somebody else's work",
        "hint": "Reading it over to catch mistakes before it goes out.",
    },
    {
        "key": "scheduled",
        "label": "Somebody works out who goes where",
        "hint": "Building the board, the run, the route, the day.",
    },
    {
        "key": "decided",
        "label": "Somebody makes a judgement call",
        "hint": "Experience decides it. There is no rule you could write down.",
    },
]

_HANDLING_KEYS = {h["key"] for h in HANDLING}


def handling_choices():
    """The answers, for the screen. A copy — nothing may edit the library."""
    return [dict(h) for h in HANDLING]


# -------------------------------------------------------------- the patterns

PATTERNS = [
    {
        "id": "re-key",
        "answers": "retyped",
        "title": "Typing the same thing in twice",
        "becomes": (
            "The second system gets it from the first. A person still looks at "
            "it once before it counts — but they read it instead of typing it."
        ),
        "low": 0.55,
        "high": 0.85,
        "effort": 2,
        "risk": 2,
        "needs": (
            "The two systems have to be able to hand information to each other. "
            "Some can and some can't, and that is the first thing to find out — "
            "before anything is built, not after."
        ),
        "why": (
            "If the two will talk to each other directly, nearly all the typing "
            "goes. If they won't, it becomes an export and an import and you "
            "keep some of the handling."
        ),
        "demo": "intake",
    },
    {
        "id": "hunt",
        "answers": "looked-up",
        "title": "Hunting for something that already exists",
        "becomes": (
            "One box to search, and it answers in seconds — across the folders, "
            "the old quotes and the email, without knowing where to look first."
        ),
        "low": 0.50,
        "high": 0.80,
        "effort": 1,
        "risk": 1,
        "needs": (
            "The documents readable in one place. Nothing bought, nothing moved "
            "to anyone else's computer."
        ),
        "why": (
            "How much this saves depends on how much of it is written down at "
            "all. What is only in somebody's head does not get faster."
        ),
        "demo": "search",
    },
    {
        "id": "write-again",
        "answers": "written",
        "title": "Writing the same thing again",
        "becomes": (
            "The first draft writes itself from what is already on the job. "
            "Somebody reads it before it goes out — that part does not change."
        ),
        "low": 0.60,
        "high": 0.85,
        "effort": 1,
        "risk": 2,
        "needs": (
            "Three or four past examples of a good one, so it sounds like your "
            "company and not like a computer."
        ),
        "why": (
            "A standard one is nearly all draft. An awkward one still needs a "
            "person to rewrite the middle of it, and you cannot tell which is "
            "which until it arrives."
        ),
        "demo": "document",
    },
    {
        "id": "chase",
        "answers": "chased",
        "title": "Chasing people",
        "becomes": (
            "It knows what is late and asks for you, in your words, on a "
            "schedule you set. You see the list — you stop sending the messages."
        ),
        "low": 0.70,
        "high": 0.90,
        "effort": 1,
        "risk": 1,
        "needs": (
            "A date on each thing that could be late. If nothing carries a date, "
            "that is the piece to fix first and it is not a computer job."
        ),
        "why": (
            "Reminders are the easiest thing here to automate. What stays is the "
            "handful where the answer is 'they aren't replying' and somebody has "
            "to pick up the phone."
        ),
        "demo": "chase",
    },
    {
        "id": "paper",
        "answers": "paper",
        "title": "It only exists on paper",
        "becomes": (
            "Captured where it happens, on the phone already in somebody's "
            "pocket, and it is in the office before the truck is."
        ),
        "low": 0.40,
        "high": 0.70,
        "effort": 2,
        "risk": 2,
        "needs": (
            "The crew willing to use it. This is the one on the page that fails "
            "for a reason that has nothing to do with software."
        ),
        "why": (
            "The typing-up disappears either way. Whether the capture itself "
            "gets faster depends entirely on whether it actually gets used in "
            "the field, and that is a people question."
        ),
        "demo": "intake",
    },
    {
        "id": "double-check",
        "answers": "checked",
        "title": "Checking somebody else's work",
        "becomes": (
            "The mistakes that are the same every time get caught before a "
            "person opens it. A person still reads the rest."
        ),
        "low": 0.30,
        "high": 0.60,
        "effort": 2,
        "risk": 2,
        "needs": (
            "A list of what actually goes wrong. Not a guess — the last twenty "
            "that came back."
        ),
        "why": (
            "Deliberately the most modest number on the page. Missing fields, "
            "wrong maths and stale prices are catchable. Somebody quoting the "
            "wrong job is not, and that is usually the expensive one."
        ),
        "demo": "checklist",
    },
    {
        "id": "who-goes-where",
        "answers": "scheduled",
        "title": "Working out who goes where",
        "becomes": (
            "A first draft of the board, with the reason written next to each "
            "one. You change what you don't like — and you start from a draft "
            "instead of a blank."
        ),
        "low": 0.30,
        "high": 0.60,
        "effort": 3,
        "risk": 2,
        "needs": (
            "Who can do what, and how long each kind of job really takes. Most "
            "companies have this in one person's head."
        ),
        "why": (
            "The routine days draft themselves. The day two people call in sick "
            "is the day it is worth having somebody who knows the customers, and "
            "no draft covers that."
        ),
        "demo": "board",
    },
    {
        "id": "judgement",
        "answers": "decided",
        "title": "A judgement call",
        "becomes": (
            "This stays with the person. What changes is that everything they "
            "need to decide is on one screen when they decide it, instead of in "
            "four places."
        ),
        # The one that says no. See the module docstring: without it the sheet
        # reads as a sales pitch, and an owner who has been sold to before will
        # hear that in the first thirty seconds.
        "low": 0.00,
        "high": 0.20,
        "effort": 2,
        "risk": 1,
        "needs": "Nothing. This is the one you should be slowest to touch.",
        "why": (
            "Nearly all of this is the deciding, and the deciding is the job. "
            "What comes off is the gathering-up beforehand."
        ),
        "demo": "",
    },
]

_BY_ID = {p["id"]: p for p in PATTERNS}
_BY_ANSWER = {p["answers"]: p for p in PATTERNS}

# Every answer has a pattern and every pattern answers something real. Checked
# at import so a typo in a new entry fails on start rather than silently
# dropping a step's only saving to zero on a client's screen.
assert _HANDLING_KEYS == set(_BY_ANSWER), (
    "handling answers and patterns are out of step: "
    + repr(_HANDLING_KEYS ^ set(_BY_ANSWER))
)


def pattern_for(handling_key):
    """The pattern that answers one handling tag, or None."""
    p = _BY_ANSWER.get(str(handling_key or "").strip())
    return dict(p) if p else None


def by_id(pattern_id):
    p = _BY_ID.get(str(pattern_id or "").strip())
    return dict(p) if p else None


def patterns_for_step(handling):
    """Every pattern that applies to a step, in library order.

    Order comes from PATTERNS rather than from whatever order the boxes were
    ticked in, so two owners who tick the same boxes get the same sheet.
    """
    picked = {str(h).strip() for h in (handling or [])}
    return [dict(p) for p in PATTERNS if p["answers"] in picked]


def savings_of(pattern):
    """(low, high) as fractions of a step's hand-time. Never one number.

    The guard is the point. `05` §8 is enforced in code everywhere else in this
    workspace, and a pattern edited later to `"low": 0.7, "high": 0.7` would
    quietly produce "saves 7 hours a month" on a client's one-pager with no
    range and no argument. This makes that a crash on start instead.
    """
    low = float(pattern.get("low", 0.0))
    high = float(pattern.get("high", 0.0))
    if not (0.0 <= low <= 1.0) or not (0.0 <= high <= 1.0):
        raise SavingsError(
            "%s: a saving is a share of the step, so it lives between 0 and 1 "
            "(got %r to %r)" % (pattern.get("id"), low, high)
        )
    if high <= low:
        raise SavingsError(
            "%s: a saving has to be a range. Low was %r and high was %r, and a "
            "single number is exactly what `05` §8 forbids on a client's page."
            % (pattern.get("id"), low, high)
        )
    return low, high


# Run the guard over the whole library at import. A bad range must not wait for
# the one owner whose workflow happens to use that pattern.
for _p in PATTERNS:
    savings_of(_p)
del _p
