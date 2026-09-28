"""demo — the part an owner touches.

The rest of this app argues about hours. This file is the thing that makes the
argument land: you paste in the actual mess — the customer's email, the voicemail
somebody typed up, the text message from the site — and it pulls out the fields
and writes the document, while they watch, in their office, on a laptop with the
wifi off.

**It is a real working demo, not a mock.** Nothing here is pre-baked to the
sample text; the same regexes run on whatever gets pasted in, including the
owner's own email if they open one. That is the entire point, and it is also the
risk: an owner who suspects the screen is a slideshow has stopped listening.

**It says what it could not find.** Every demo returns `missed` alongside
`found`, and the screen shows both. A demo that only shows its wins is a demo
that gets believed once — the first time it misses something in front of the
owner and did not say so, the whole conversation is over. Reporting the misses
is also what makes the follow-on honest: those are the fields a person still
has to fill in.

**Nothing pasted here goes anywhere.** No network calls, no model, no cloud.
The extraction is regular expressions in the standard library, which is a real
limitation and is said plainly on screen rather than implied away.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

__all__ = ["FIELDS", "extract", "fill", "chase", "checklist", "run", "DEMOS"]


# ------------------------------------------------------------------ helpers

def _clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _trim(s):
    """Drop sentence punctuation that got swept up with the value.

    `CB-330.` and `3300 Appling Road.` are the regex picking up the full stop at
    the end of the sentence, and on screen they read as a tool that is nearly
    right — which is worse than one that is obviously right or obviously silent.
    """
    s = _clean(s)
    while s and s[-1] in ".,;:":
        s = s[:-1].rstrip()
    return s


def _first(text, patterns, flags=0):
    """First pattern that hits, with which one hit. The `found_by` line on the
    screen is this — an owner asking 'how did it know that?' gets an answer.

    **Case-sensitive by default**, and every keyword below wears its own
    `(?i:…)` instead. Running the whole thing under IGNORECASE looks harmless
    and quietly destroys the one signal that separates a person's name from the
    words around it: `[A-Z]` stops meaning "a capital letter". That is how an
    earlier version read *this is Dana at Northside* and put **Dana at** on the
    screen as the customer's name.
    """
    for entry in patterns:
        label, rx = entry[0], entry[1]
        validate = entry[2] if len(entry) > 2 else None
        for m in re.finditer(rx, text, flags):
            value = _trim(m.group("v") if "v" in (m.groupdict() or {}) else m.group(0))
            if not value:
                continue
            if validate and not validate(value):
                continue
            return value, label
    return "", ""


def _valid_slashed_date(value):
    """Reject a slashed date whose numbers cannot be a month and a day in
    either order. `12/45` has no reading where 45 is a day (max 31) or a
    month (max 12) — that is malformed, not merely ambiguous, and the demo's
    contract is to catch malformed values. `03/04` is left alone: both
    readings are in range, and which one is meant is not this function's
    business to decide.
    """
    bits = value.split("/")
    if len(bits) < 2:
        return True
    a, b = int(bits[0]), int(bits[1])

    def month_ok(n):
        return 1 <= n <= 12

    def day_ok(n):
        return 1 <= n <= 31

    return (month_ok(a) and day_ok(b)) or (day_ok(a) and month_ok(b))


# ------------------------------------------------------------------- fields
#
# Ordered as they would appear on a job card, because that is the order the
# owner reads them back in.

_MONTHS = ("january|february|march|april|may|june|july|august|september|"
           "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")

FIELDS = [
    {
        "key": "name",
        "label": "Who it's from",
        "patterns": [
            ("a line that introduces them",
             r"(?i:my name is|this is|it'?s|i'?m)\s+(?P<v>[A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+)?)\b"),
            ("a sign-off at the end",
             r"(?i:regards|thanks|thank you|cheers|sincerely)\s*,?\s*\n+\s*(?P<v>[A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+)?)\s*$"),
            ("who the message came from",
             r"(?i:text|call|voicemail|message|note)\s+(?i:from)\s+(?P<v>[A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+)?)\b"),
            ("a From: line", r"(?im:^\s*from\s*:\s*)(?P<v>[^<\n]{2,60}?)\s*(?:<|$)"),
        ],
    },
    {
        "key": "company",
        # No loose fallback here on purpose. An earlier version matched "the
        # capitalised words after `at` or `with`", which produced *any questions.
        # Budget is* as a company name — and a field that is confidently wrong on
        # the screen an owner is reading costs more than a field left empty. Both
        # patterns below can only fire on something that really is a company:
        # a legal suffix, or the domain they emailed from.
        "label": "Company",
        "patterns": [
            ("a company suffix",
             r"(?P<v>[A-Z][A-Za-z&'’-]*(?:\s+[A-Z][A-Za-z&'’-]*){0,3}\s+(?:Inc|LLC|L\.L\.C|Ltd|Co|Company|Corp|Corporation|Services|Service|Supply|Industries|Mechanical|Heating|Plumbing|Electric|Electrical|Construction|Manufacturing|Machine|Contracting)\b\.?)"),
            ("the domain they emailed from",
             r"[\w.+-]+@(?P<v>[\w-]+\.[\w.-]{2,})"),
        ],
    },
    {
        "key": "phone",
        "label": "Phone",
        "patterns": [
            ("a ten-digit number",
             r"(?P<v>(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?i:x|ext\.?)\s*\d{1,6})?)"),
        ],
    },
    {
        "key": "email",
        "label": "Email",
        "patterns": [("an @ with a dot after it",
                      r"(?P<v>[\w.+-]+@[\w-]+\.[\w.-]{2,})")],
    },
    {
        "key": "address",
        "label": "Address",
        "patterns": [
            ("a number then a street type",
             r"(?P<v>\d{1,6}\s+[\w.'’-]+(?:\s+[\w.'’-]+){0,4}\s+(?i:st|street|rd|road|ave|avenue|dr|drive|ln|lane|blvd|boulevard|hwy|highway|way|ct|court|pkwy|parkway|cir|circle|trl|trail)\b\.?(?:[\s,]+(?i:ste|suite|unit|apt|bldg)\.?\s*[\w-]+)?)"),
        ],
    },
    {
        "key": "when",
        "label": "When they want it",
        "patterns": [
            ("a written date",
             r"(?P<v>(?i:%s)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)" % _MONTHS),
            ("a slashed date", r"(?P<v>\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
             _valid_slashed_date),
            # A wanted-day beats a mentioned-day. "We have patients Monday so we
            # need somebody out Friday" holds two weekdays and only one of them
            # is the answer; asking for the verb first is what separates them.
            ("a day they asked for",
             r"(?i:need|want|by|out|come|be there|scheduled?|book(?:ed)?)\s+(?:\w+\s+){0,2}?(?P<v>(?i:mon|tues|wednes|thurs|fri|satur|sun)day)"),
            ("a day of the week",
             r"(?P<v>(?i:(?:this |next |by )?(?:mon|tues|wednes|thurs|fri|satur|sun)day))"),
            ("a word that means now",
             r"(?P<v>(?i:asap|as soon as possible|today|tomorrow|right away|urgent|emergency))"),
        ],
    },
    {
        "key": "reference",
        "label": "Their reference",
        # The value has to contain a digit. Without the lookahead this read
        # "the job has to happen today" and offered **has** as the customer's
        # job number — a reference with no number in it is not a reference.
        "patterns": [
            ("a PO or job number",
             r"(?i:p\.?o\.?|purchase order|job|work order|wo|ticket|quote|invoice)\s*#?\s*[:.]?\s*"
             r"(?P<v>(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{2,20})"),
        ],
    },
    {
        "key": "part",
        "label": "Part or model",
        "patterns": [
            ("a labelled part number",
             r"(?i:part|model|item|sku|p/n|mfr)\s*#?\s*[:.]?\s*"
             r"(?P<v>(?=[A-Z0-9./-]*\d)[A-Z0-9][A-Z0-9./-]{2,24})"),
            ("something that looks like a part number",
             r"\b(?P<v>[A-Z]{2,4}[-/]?\d{3,6}(?:[-/][A-Z0-9]{1,5})?)\b"),
        ],
    },
    {
        "key": "quantity",
        "label": "How many",
        "patterns": [
            ("a count next to a unit",
             r"\b(?P<v>\d{1,5}(?:,\d{3})*)\s*(?i:x\b|ea\b|each\b|pcs?\b|pieces?\b|units?\b|off\b)"),
            ("'quantity' spelled out", r"(?i:qty|quantity)\s*[:.]?\s*(?P<v>\d{1,6})"),
        ],
    },
    {
        "key": "money",
        "label": "Money mentioned",
        "patterns": [("a dollar figure", r"(?P<v>\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")],
    },
]

_FIELD_BY_KEY = {f["key"]: f for f in FIELDS}


def extract(text, keys=None):
    """Pull fields out of pasted text. Returns found, missed, and how.

    `missed` is not a leftover — it is half the output. See the module note.
    """
    text = str(text or "")
    wanted = [k for k in (keys or [f["key"] for f in FIELDS]) if k in _FIELD_BY_KEY]
    found, missed = [], []
    # One value cannot be two fields. `WO-2214` matches both the job-number rule
    # and the looks-like-a-part-number rule, and a card showing the same string
    # as the reference *and* the part is a card the owner stops trusting. First
    # field to claim it keeps it; the later one reports a miss and says why.
    claimed = {}
    for key in wanted:
        spec = _FIELD_BY_KEY[key]
        value, how = _first(text, spec["patterns"])
        if value and value.casefold() in claimed:
            missed.append({
                "key": key, "label": spec["label"],
                "why": "The only thing that matched (%s) is already down as: %s."
                       % (value, claimed[value.casefold()]),
            })
            continue
        if value:
            claimed[value.casefold()] = spec["label"]
            found.append({"key": key, "label": spec["label"], "value": value,
                          "found_by": how})
        else:
            missed.append({"key": key, "label": spec["label"],
                           "why": "Nothing in the text looked like this."})
    return {
        "found": found,
        "missed": missed,
        "record": {f["key"]: f["value"] for f in found},
        "chars": len(text),
        "how": ("Read %d characters and looked for %d kinds of thing. "
                "Found %d, missed %d."
                % (len(text), len(wanted), len(found), len(missed))),
    }


# ---------------------------------------------------------- writing it back

_SLOT = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def fill(template, record):
    """Write the document from the record.

    A slot with nothing behind it becomes `[ Who it's from — ask ]` rather than
    an empty space. An owner reading a draft with a hole in it knows what to do;
    an owner reading a draft with a silent gap sends it.
    """
    record = {str(k): _clean(v) for k, v in (record or {}).items()}
    gaps = []

    def sub(m):
        key = m.group(1)
        value = record.get(key, "")
        if value:
            return value
        label = _FIELD_BY_KEY.get(key, {}).get("label", key.replace("_", " "))
        if key not in [g["key"] for g in gaps]:
            gaps.append({"key": key, "label": label})
        return "[ %s — ask ]" % label

    text = _SLOT.sub(sub, str(template or ""))
    return {"text": text, "gaps": gaps,
            "how": "%d slots filled from the record, %d left for a person."
                   % (len(_SLOT.findall(str(template or ""))) - len(gaps), len(gaps))}


DOCUMENT_TEMPLATES = {
    "acknowledgement": (
        "Subject: Got it — {{reference}}\n\n"
        "{{name}},\n\n"
        "Thanks for this. We have it down as:\n\n"
        "  What:     {{part}} × {{quantity}}\n"
        "  Where:    {{address}}\n"
        "  Wanted:   {{when}}\n"
        "  Your ref: {{reference}}\n\n"
        "If any of that is wrong, reply and we'll fix it before it goes any further.\n"
        "You'll have a price back from us before the end of the day.\n"
    ),
    "work-order": (
        "WORK ORDER — {{reference}}\n"
        "================================\n"
        "Customer:  {{name}} ({{company}})\n"
        "Phone:     {{phone}}\n"
        "Site:      {{address}}\n"
        "Wanted:    {{when}}\n"
        "\n"
        "Job\n"
        "---\n"
        "{{part}}  × {{quantity}}\n"
        "\n"
        "Assigned to: ______________________   Est. hours: __________\n"
        "Parts pulled: ____________________    Date done:  __________\n"
    ),
    "quote": (
        "QUOTE — {{reference}}\n"
        "For: {{company}} / {{name}}\n"
        "Site: {{address}}\n"
        "Needed by: {{when}}\n"
        "\n"
        "  Item            {{part}}\n"
        "  Quantity        {{quantity}}\n"
        "  Unit price      $__________\n"
        "  Total           $__________\n"
        "\n"
        "Valid 30 days. Prices subject to supplier confirmation.\n"
        "Questions: {{phone}}\n"
    ),
}


# --------------------------------------------------------------- the chasing

def chase(rows, today=None):
    """What is late, how late, and the message that would go out.

    `today` is an argument rather than a call to the clock so a test can pin it.
    """
    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = datetime.strptime(today[:10], "%Y-%m-%d").date()

    out, unreadable = [], []
    for raw in (rows or []):
        if not isinstance(raw, dict):
            continue
        who = _clean(raw.get("who")) or "Someone"
        what = _clean(raw.get("what")) or "something"
        due_raw = _clean(raw.get("due"))
        try:
            due = datetime.strptime(due_raw[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            unreadable.append({"who": who, "what": what, "due": due_raw,
                               "why": "I can't read that date. It needs to look like 2026-08-14."})
            continue
        days = (today - due).days
        out.append({
            "who": who, "what": what, "due": due.isoformat(), "days_late": days,
            "state": "late" if days > 0 else ("due today" if days == 0 else "not yet"),
            "message": ("%s — following up on %s, which was due %s. Where are we on it?"
                        % (who, what, due.isoformat())) if days >= 0 else "",
        })
    out.sort(key=lambda r: -r["days_late"])
    late = [r for r in out if r["days_late"] > 0]
    return {
        "rows": out,
        "unreadable": unreadable,
        "late_count": len(late),
        "how": ("%d things checked against %s. %d late, %d due today, %d not yet"
                % (len(out), today.isoformat(), len(late),
                   sum(1 for r in out if r["days_late"] == 0),
                   sum(1 for r in out if r["days_late"] < 0))
                + (", %d with a date I couldn't read" % len(unreadable) if unreadable else "")
                + "."),
    }


# ------------------------------------------------------------- the checking

def checklist(record, required=None):
    """The mistakes that are the same every time.

    Modest on purpose — it matches the `double-check` pattern's own claim. It
    catches missing and malformed, and says out loud that it cannot catch wrong.
    """
    record = record or {}
    required = required or ["name", "phone", "address", "part", "quantity"]
    problems, passed = [], []
    for key in required:
        label = _FIELD_BY_KEY.get(key, {}).get("label", key)
        value = _clean(record.get(key))
        if not value:
            problems.append({"key": key, "label": label, "problem": "Missing."})
            continue
        if key == "phone" and len(re.sub(r"\D", "", value)) < 10:
            problems.append({"key": key, "label": label,
                             "problem": "That is not a full number — %s" % value})
            continue
        if key == "quantity" and not re.search(r"\d", value):
            problems.append({"key": key, "label": label,
                             "problem": "No number in it — %s" % value})
            continue
        passed.append({"key": key, "label": label, "value": value})
    return {
        "problems": problems,
        "passed": passed,
        "how": "%d things checked, %d passed, %d to fix."
               % (len(required), len(passed), len(problems)),
        "cannot_catch": (
            "This catches missing and malformed. It cannot catch wrong — a "
            "correctly-formatted quote for the wrong job passes every check "
            "here, and that is usually the expensive one."
        ),
    }


# ----------------------------------------------------------------- dispatch

DEMOS = {
    "intake":   {"title": "Paste the mess, get the job card",
                 "blurb": "An email, a voicemail typed up, a text from site — it pulls the fields out."},
    "document": {"title": "The document writes itself",
                 "blurb": "Same record, straight into an acknowledgement, a work order or a quote."},
    "chase":    {"title": "What's late, and the message",
                 "blurb": "Dates in, overdue list out, with the follow-up already written."},
    "checklist": {"title": "Catch it before it goes out",
                  "blurb": "The mistakes that are the same every time. It says what it can't catch."},
    "search":   {"title": "One box, everything answers",
                 "blurb": "Handled by the Knowledge Base Builder — that one is already built."},
    "board":    {"title": "A first draft of the day",
                 "blurb": "Not built yet. Named here so the sheet doesn't imply it exists."},
}


def run(key, payload):
    """One entry point, so the browser never has to know which function to call."""
    key = str(key or "").strip()
    payload = payload if isinstance(payload, dict) else {}
    if key == "intake":
        return extract(payload.get("text"), payload.get("fields"))
    if key == "document":
        name = str(payload.get("template") or "acknowledgement")
        template = DOCUMENT_TEMPLATES.get(name)
        if template is None:
            raise KeyError("No document called %r. Try: %s."
                           % (name, ", ".join(sorted(DOCUMENT_TEMPLATES))))
        record = payload.get("record")
        if not record and payload.get("text"):
            record = extract(payload["text"])["record"]
        out = fill(template, record or {})
        out["template"] = name
        return out
    if key == "chase":
        return chase(payload.get("rows"), payload.get("today"))
    if key == "checklist":
        record = payload.get("record")
        if not record and payload.get("text"):
            record = extract(payload["text"])["record"]
        return checklist(record or {}, payload.get("required"))
    raise KeyError(
        "There is no live demo called %r. The ones that run here are: %s."
        % (key, ", ".join(k for k, v in DEMOS.items() if k in
                          ("intake", "document", "chase", "checklist")))
    )
