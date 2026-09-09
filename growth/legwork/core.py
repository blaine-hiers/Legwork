"""core — the arithmetic, and the one-pager it produces.

Every number this file emits carries the sum that produced it. That is not a
nicety: `05` §8 forbids a figure on a client's page without visible working, and
the quietest possible way to break that rule is to compute a number correctly
and then lose its arithmetic at a boundary. So `how` travels with the value, all
the way to the printed page.

Two things it deliberately will not do:

**It will not turn hours into money unless the owner gives it a rate.** There is
a standing temptation to multiply saved hours by an invented labour cost, and it
would make every sheet look better. What it would actually be is a made-up
number wearing a dollar sign. If nobody says what an hour costs, the sheet says
hours.

**It will not add the savings up and call it a total the business gets back.**
Two steps done by the same person do not free two people, and a saved hour is
not a banked hour unless somebody does something else with it. The totals here
are labelled as hand-time removed from the work, which is what was measured, and
the one-pager says so out loud.
"""

from __future__ import annotations

import patterns

__all__ = ["blank_demo", "normalize", "analyze", "to_markdown", "to_text",
           "from_flowmap", "HANDOFF_FORMAT", "HANDOFF_VERSION"]

DEFAULT_RUNS_PER_MONTH = 0.0
MAX_STEPS = 40          # a first conversation that needs 40 steps needs a map, not a sheet

HANDOFF_FORMAT = "flowmap-handoff"
HANDOFF_VERSION = 1


# ------------------------------------------------------------------ numbers

def _num(value, default=0.0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return float(default)
    if n != n or n in (float("inf"), float("-inf")):   # NaN / inf
        return float(default)
    return max(0.0, min(n, 1e9))


def _text(value, default=""):
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _round(n, places=1):
    r = round(float(n) + 0.0, places)
    return int(r) if places == 0 or r == int(r) else r


def _hours(minutes):
    return _round(minutes / 60.0, 1)


def _band(hours):
    """Impact 1–5 from hours a month. Bands, not a curve — an owner can check a
    band against their own sense of the place, and cannot check a curve."""
    if hours < 2:
        return 1
    if hours < 6:
        return 2
    if hours < 15:
        return 3
    if hours < 30:
        return 4
    return 5


# ------------------------------------------------------------------ the doc

def blank_demo(name="Untitled"):
    return {
        "name": name,
        "client": "",
        "industry": "",
        "steps": [],
        "hourly_cost": 0.0,     # 0 means "nobody said", and the sheet stays in hours
        "notes": "",
    }


def _normalize_step(raw, index):
    raw = raw if isinstance(raw, dict) else {}
    handling = []
    seen = set()
    for h in (raw.get("handling") or []):
        key = _text(h)
        if key and key not in seen and patterns.pattern_for(key):
            seen.add(key)
            handling.append(key)
    return {
        "id": _text(raw.get("id")) or "s%d" % (index + 1),
        "name": _text(raw.get("name")) or "Untitled step",
        "who": _text(raw.get("who")),
        "system": _text(raw.get("system")),
        "minutes": _num(raw.get("minutes")),
        "runs_per_month": _num(raw.get("runs_per_month"), DEFAULT_RUNS_PER_MONTH),
        "handling": handling,
        "note": _text(raw.get("note")),
    }


def normalize(doc):
    """Anything demo-shaped in, a clean copy out. Everything downstream may
    assume this ran."""
    doc = dict(doc or {})
    steps = []
    seen = set()
    for i, raw in enumerate(doc.get("steps") or []):
        step = _normalize_step(raw, i)
        if step["id"] in seen:
            step["id"] = "s%d" % (i + 1)
        if step["id"] in seen:          # still colliding: drop rather than shadow
            continue
        seen.add(step["id"])
        steps.append(step)
        if len(steps) >= MAX_STEPS:
            break

    out = {
        "id": _text(doc.get("id")) or None,
        "name": _text(doc.get("name")) or "Untitled",
        "client": _text(doc.get("client")),
        "industry": _text(doc.get("industry")),
        "notes": _text(doc.get("notes")),
        "hourly_cost": _num(doc.get("hourly_cost")),
        "steps": steps,
    }
    for key in ("created", "updated", "starter", "from_map"):
        if doc.get(key) is not None:
            out[key] = doc[key]
    return out


# ----------------------------------------------------------------- analysis

# A step never goes to zero. Somebody still opens it, glances at it, signs it.
# Every step's range is squeezed by this before it is shown, which is why no
# figure this app produces ever reads as 100% — and why a step with two heavy
# patterns on it does not quietly claim the whole step back.
#
# Squeezed rather than clamped, deliberately. A clamp at 0.9 flattens both ends
# of a wide range onto the ceiling and hands back 0.9–0.9: a single point, on a
# client's page, which is the one thing `05` §8 forbids. Multiplying keeps the
# width of the band proportional, so a range can never collapse into a number.
STEP_CEILING = 0.90


def _compose(fractions):
    """Combine several patterns on one step. Not a sum.

    Adding them is wrong twice over. It runs past 100% with two ordinary
    patterns — and then whatever caps it collapses the range. It is also just
    not how the work behaves: if one pattern takes 60% of a step away, the next
    one can only act on the 40% that is left, not on the original whole.

    So each pattern takes its share of what remains, and what remains is what
    gets multiplied. Two patterns at 60% leave 0.4 × 0.4 = 16%, not −20%.
    """
    remaining = 1.0
    for f in fractions:
        remaining *= (1.0 - f)
    return 1.0 - remaining


def _step_analysis(step, hourly_cost):
    """One step: what it costs today, and what the patterns would take off it."""
    per_run = step["minutes"]
    runs = step["runs_per_month"]
    minutes_month = per_run * runs

    picked = patterns.patterns_for_step(step["handling"])
    rows = []
    lows, highs = [], []
    effort = risk = 0
    for p in picked:
        lo, hi = patterns.savings_of(p)
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "becomes": p["becomes"],
            "needs": p["needs"],
            "why": p["why"],
            "demo": p.get("demo") or "",
            "share_low": int(round(lo * 100)),
            "share_high": int(round(hi * 100)),
            "how": (
                "%s min × %s a month = %s hrs of hand-time. This one takes "
                "%d%%–%d%% of what reaches it."
                % (_round(per_run, 0), _round(runs, 0), _hours(minutes_month),
                   round(lo * 100), round(hi * 100))
            ),
        })
        lows.append(lo)
        highs.append(hi)
        effort = max(effort, int(p["effort"]))
        risk = max(risk, int(p["risk"]))

    low_frac = _compose(lows) * STEP_CEILING
    high_frac = _compose(highs) * STEP_CEILING

    # The invariant the whole app rests on. `_compose` and the ceiling both
    # preserve a band by construction, so this can only fire if somebody
    # changes the model later -- which is exactly when it needs to fire.
    if picked and not high_frac > low_frac:
        raise patterns.SavingsError(
            "step %r collapsed to a single figure (%r). A saving on a client's "
            "page is a range or it is nothing." % (step.get("name"), low_frac)
        )

    saved_low = _hours(minutes_month * low_frac)
    saved_high = _hours(minutes_month * high_frac)
    mid = (saved_low + saved_high) / 2.0

    impact = _band(mid) if picked else 0
    # `05`'s own scoring, unchanged: Priority = Impact × 2 − Effort − Risk.
    priority = (impact * 2) - effort - risk if picked else -99

    out = {
        "id": step["id"],
        "name": step["name"],
        "who": step["who"],
        "system": step["system"],
        "minutes": _round(per_run, 0),
        "runs_per_month": _round(runs, 0),
        "hours_month": _hours(minutes_month),
        "hours_how": "%s min × %s a month ÷ 60 = %s hrs"
                     % (_round(per_run, 0), _round(runs, 0), _hours(minutes_month)),
        "patterns": rows,
        "saved_low": saved_low,
        "saved_high": saved_high,
        # Kept alongside the hours because hours round: a step worth two minutes
        # a month shows 0.0–0.0 hrs, and the percentages are what stop that
        # reading as a single-point claim on the screen.
        "share_low": int(round(low_frac * 100)),
        "share_high": int(round(high_frac * 100)),
        "saved_how": (
            "%s hrs of hand-time a month, %d%%–%d%% of it addressed = %s–%s hrs"
            % (_hours(minutes_month), round(low_frac * 100), round(high_frac * 100),
               saved_low, saved_high)
            + (". Two patterns on one step don't add up — the second one only "
               "works on what the first one left, and a tenth of every step is "
               "left with a person on purpose." if len(rows) > 1 else
               ". A tenth of the step is left with a person on purpose.")
        ) if picked else "Nothing was ticked for this step, so nothing is claimed for it.",
        "impact": impact,
        "effort": effort,
        "risk": risk,
        "priority": priority,
        "priority_how": (
            "Impact %d × 2 − effort %d − risk %d = %d"
            % (impact, effort, risk, priority)
        ) if picked else "",
        "note": step["note"],
    }
    if hourly_cost > 0:
        out["money_low"] = _round(saved_low * hourly_cost, 0)
        out["money_high"] = _round(saved_high * hourly_cost, 0)
        out["money_how"] = (
            "%s–%s hrs × $%s an hour = $%s–$%s a month"
            % (saved_low, saved_high, _round(hourly_cost, 0),
               _round(saved_low * hourly_cost, 0), _round(saved_high * hourly_cost, 0))
        )
    return out


def analyze(doc):
    m = normalize(doc)
    rate = m["hourly_cost"]
    rows = [_step_analysis(s, rate) for s in m["steps"]]

    total_hours = sum(r["hours_month"] for r in rows)
    low = _round(sum(r["saved_low"] for r in rows), 1)
    high = _round(sum(r["saved_high"] for r in rows), 1)

    scored = [r for r in rows if r["patterns"]]
    scored.sort(key=lambda r: (-r["priority"], -r["saved_high"], r["name"]))
    first = scored[0] if scored else None

    warnings = []
    if not m["steps"]:
        warnings.append("Nothing described yet. One step is enough to start.")
    no_runs = [r["name"] for r in rows if r["runs_per_month"] <= 0]
    if no_runs:
        warnings.append(
            "No 'how often' on: " + ", ".join(no_runs[:4])
            + ("…" if len(no_runs) > 4 else "")
            + ". Those steps count as zero — a minute nobody spends is not a saving."
        )
    no_minutes = [r["name"] for r in rows if r["minutes"] <= 0]
    if no_minutes:
        warnings.append(
            "No 'how long' on: " + ", ".join(no_minutes[:4])
            + ("…" if len(no_minutes) > 4 else "") + ". Same again — they count as zero."
        )
    untouched = [r["name"] for r in rows if not r["patterns"]]
    if untouched:
        warnings.append(
            "Nothing ticked on: " + ", ".join(untouched[:4])
            + ("…" if len(untouched) > 4 else "")
            + ". They are on the sheet as work, with no saving claimed."
        )
    if rate <= 0:
        warnings.append(
            "No hourly cost given, so this stays in hours. That is the honest "
            "default: a dollar figure built on a rate nobody stated is a guess "
            "with a dollar sign on it."
        )

    return {
        "steps": rows,
        "totals": {
            "steps": len(rows),
            "hours_month": _round(total_hours, 1),
            "saved_low": low,
            "saved_high": high,
            "how": (
                "Every step's hand-time added up is %s hrs a month. The patterns "
                "ticked address %s–%s hrs of that."
                % (_round(total_hours, 1), low, high)
            ),
            "share_low": int(round((low / total_hours) * 100)) if total_hours else 0,
            "share_high": int(round((high / total_hours) * 100)) if total_hours else 0,
        },
        "first": first,
        "warnings": warnings,
    }


# ------------------------------------------------------------ the one-pager

_STANDING_NOTE = (
    "These are your numbers, not an industry average — every figure above came "
    "from what you said in this conversation, and the sums are written out so "
    "you can argue with them. The ranges are wide because nothing here has been "
    "measured in your office yet. Nothing on this page is a promise."
)

_NOT_A_TOTAL = (
    "Hours here means hand-time coming off the work. It is not the same as a "
    "person freed up or money in the bank — two steps done by the same person "
    "do not free two people, and an hour saved is only worth something if it "
    "goes somewhere useful."
)

_NOT_ALL_OF_IT = (
    "No step on this page goes to zero. A tenth of each one is left with a "
    "person whatever gets built, and where two things could be done to the same "
    "step they do not add up — the second one only works on what the first one "
    "left. That is why nothing here reads as 100%."
)


def _range(low, high, unit="hrs"):
    return "%s–%s %s" % (low, high, unit)


def to_markdown(doc, analysis=None):
    m = normalize(doc)
    a = analysis or analyze(m)
    t = a["totals"]
    who = m["client"] or m["name"]

    out = []
    out.append("# %s — what could come off your plate" % who)
    if m["industry"]:
        out.append("")
        out.append("*%s*" % m["industry"])
    out.append("")
    out.append("## The short version")
    out.append("")
    if t["steps"]:
        out.append("You described **%d steps** taking **%s hours a month** of "
                   "somebody's hands." % (t["steps"], t["hours_month"]))
        out.append("")
        out.append("Of that, **%s** looks addressable — %d%% to %d%% of it."
                   % (_range(t["saved_low"], t["saved_high"]),
                      t["share_low"], t["share_high"]))
        out.append("")
        out.append("> %s" % t["how"])
    else:
        out.append("Nothing described yet.")
    out.append("")

    if a["first"]:
        f = a["first"]
        out.append("## Start here")
        out.append("")
        out.append("**%s**" % f["name"])
        out.append("")
        out.append("- Takes %s hours a month today (%s)" % (f["hours_month"], f["hours_how"]))
        out.append("- Addressable: **%s a month**" % _range(f["saved_low"], f["saved_high"]))
        out.append("- Why this one first: %s" % f["priority_how"])
        if f.get("money_how"):
            out.append("- In money: %s" % f["money_how"])
        out.append("")
        for p in f["patterns"]:
            out.append("**%s** — %s" % (p["title"], p["becomes"]))
            out.append("")
            out.append("- Arithmetic: %s" % p["how"])
            out.append("- Needs: %s" % p["needs"])
            out.append("- Why the range is that wide: %s" % p["why"])
            out.append("")

    out.append("## Everything you described")
    out.append("")
    out.append("| Step | Who | Today | Addressable | Why that order |")
    out.append("|---|---|---|---|---|")
    for r in a["steps"]:
        out.append("| %s | %s | %s hrs/mo | %s | %s |" % (
            r["name"].replace("|", "/"),
            (r["who"] or "—").replace("|", "/"),
            r["hours_month"],
            _range(r["saved_low"], r["saved_high"]) if r["patterns"] else "not claimed",
            r["priority_how"] or "nothing ticked",
        ))
    out.append("")

    if a["warnings"]:
        out.append("## What this sheet does not cover")
        out.append("")
        for w in a["warnings"]:
            out.append("- %s" % w)
        out.append("")

    out.append("---")
    out.append("")
    out.append(_NOT_A_TOTAL)
    out.append("")
    out.append(_NOT_ALL_OF_IT)
    out.append("")
    out.append(_STANDING_NOTE)
    out.append("")
    return "\n".join(out)


def to_text(doc, analysis=None):
    """The same sheet as plain text, for pasting into an email."""
    m = normalize(doc)
    a = analysis or analyze(m)
    t = a["totals"]
    lines = ["%s — what could come off your plate" % (m["client"] or m["name"]), ""]
    lines.append("%d steps, %s hours a month of hand-time."
                 % (t["steps"], t["hours_month"]))
    lines.append("Addressable: %s a month (%d%%-%d%%)."
                 % (_range(t["saved_low"], t["saved_high"]),
                    t["share_low"], t["share_high"]))
    lines.append("  %s" % t["how"])
    lines.append("")
    if a["first"]:
        f = a["first"]
        lines.append("START HERE: %s" % f["name"])
        lines.append("  Today: %s" % f["hours_how"])
        lines.append("  Addressable: %s" % f["saved_how"])
        lines.append("  Order: %s" % f["priority_how"])
        for p in f["patterns"]:
            lines.append("  - %s: %s" % (p["title"], p["becomes"]))
            lines.append("    %s" % p["how"])
        lines.append("")
    for w in a["warnings"]:
        lines.append("* %s" % w)
    if a["warnings"]:
        lines.append("")
    lines.append(_NOT_A_TOTAL)
    lines.append("")
    lines.append(_NOT_ALL_OF_IT)
    lines.append("")
    lines.append(_STANDING_NOTE)
    return "\n".join(lines)


# ------------------------------------------------- coming in from the mapper

# What each of the mapper's pain levels suggests, and nothing more. A map does
# not record what happens to the information -- that question is only ever asked
# here -- so an import arrives with the times and the names filled in and the
# handling **empty on purpose**. Guessing it would put ticks on a client's sheet
# that the client never said, which is the one thing this app must never do.

def from_flowmap(handoff):
    """Turn a workflow-mapper handoff into a starting demo.

    Refused in plain English if it came from a newer mapper, the same contract
    the report builder holds — a half-read file is worse than a refused one.
    """
    if not isinstance(handoff, dict):
        raise ValueError("That file isn't a workflow map I can read.")
    fmt = handoff.get("format")
    if fmt != HANDOFF_FORMAT:
        raise ValueError(
            "That file says it is %r. I can only read a %r file — the one "
            "Workflow Mapper writes from Export → Send to the report builder."
            % (fmt or "not labelled", HANDOFF_FORMAT)
        )
    try:
        version = int(handoff.get("v", 0))
    except (TypeError, ValueError):
        version = 0
    if version > HANDOFF_VERSION:
        raise ValueError(
            "That map came from a newer Workflow Mapper (file version %d, this "
            "app reads %d). Rather than half-read it, I've stopped. Update this "
            "app." % (version, HANDOFF_VERSION)
        )

    src = handoff.get("source") or {}
    m = handoff.get("map") or {}
    steps = []
    for i, s in enumerate(m.get("steps") or []):
        if not isinstance(s, dict):
            continue
        if s.get("kind") in ("start", "end"):
            continue
        steps.append({
            "id": _text(s.get("id")) or "s%d" % (i + 1),
            "name": _text(s.get("name")) or "Untitled step",
            "who": _text(s.get("role")),
            "system": _text(s.get("system")),
            "minutes": _num(s.get("touch_min")),
            "runs_per_month": 0.0,      # a map counts one run; how often is a question
            "handling": [],             # never guessed — see the note above
            "note": _text(s.get("note")),
        })

    return normalize({
        "name": _text(src.get("name")) or _text(m.get("name")) or "From a workflow map",
        "client": _text(src.get("client")) or _text(m.get("client")),
        "industry": _text(src.get("industry")) or _text(m.get("industry")),
        "steps": steps,
        "from_map": _text(src.get("map_id")) or True,
    })
