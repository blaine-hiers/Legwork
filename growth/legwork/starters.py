"""starters — a recognisable first screen, per industry. Loaded from files.

A cold prospect gives you about ten seconds to look like you know their
business. Starting from an empty form spends all ten of them. So each starter
puts a workflow on screen that an owner in that trade recognises immediately —
in their words, not in process-mapping words.

**The starters are content, not code.** They live in `starters/*.json` next to
this file and are edited with a text editor. That is the whole point: the rule
this app inherits from `04` §3 is *when an owner uses a different word, change
the template*, and a template written in Python is a template that only gets
changed when somebody is in the mood to edit Python. A starter is a file, and
**adding a file adds a starter** — the same bet the hub makes about apps.

**Every number in these files is a starting guess and the app says so on
screen.** That warning is not politeness, it is what stops this app producing a
fabricated client sheet: a starter left unedited would put times and volumes
nobody said into a document with the owner's company name at the top.

So a starter file **cannot carry a volume at all**. `runs_per_month` is forced
to zero on the way in and a file that tries to set one is reported on screen
rather than quietly obeyed. Zero means the sheet claims nothing until somebody
answers "how often?" out loud, and `core`'s warnings name every step still
sitting at zero. Minutes *are* seeded, because "about twenty minutes?" is a
question an owner corrects in one breath — nobody can correct a number they
were never asked for.

**A broken file never stops the app.** It is dropped, and what was wrong with
it is reported to the screen — same standing as a feed that 404s in AI Radar. A
starter that silently vanished would look exactly like one nobody had written.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["list_starters", "get_starter", "problems", "reload", "STARTERS_DIR"]

STARTERS_DIR = Path(__file__).resolve().parent / "starters"

_REQUIRED = ("key", "title", "industry", "blurb", "asks", "steps")

_cache = None
_problems = []


def _fault(name, why):
    _problems.append({"file": name, "why": why})


def _clean_step(raw, index, name):
    if not isinstance(raw, dict):
        return None
    handling = [str(h).strip() for h in (raw.get("handling") or []) if str(h).strip()]
    try:
        minutes = max(0.0, float(raw.get("minutes") or 0))
    except (TypeError, ValueError):
        _fault(name, "step %d has a 'minutes' that isn't a number — treated as 0."
                     % (index + 1))
        minutes = 0.0
    if raw.get("runs_per_month"):
        _fault(name, "step %d sets 'runs_per_month'. Dropped — a volume nobody "
                     "was asked for must not reach a client's sheet."
                     % (index + 1))
    return {
        "name": str(raw.get("name") or "").strip() or "Untitled step",
        "who": str(raw.get("who") or "").strip(),
        "system": str(raw.get("system") or "").strip(),
        "minutes": minutes,
        "runs_per_month": 0,        # forced, never read from the file
        "handling": handling,
        "note": str(raw.get("note") or "").strip(),
    }


def _load_one(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _fault(path.name, "I couldn't read it: %s" % e)
        return None
    if not isinstance(raw, dict):
        _fault(path.name, "The file has to hold one starter as a JSON object.")
        return None
    missing = [f for f in _REQUIRED if not raw.get(f)]
    if missing:
        _fault(path.name, "Missing: %s." % ", ".join(missing))
        return None
    steps = [s for s in (_clean_step(st, i, path.name)
                         for i, st in enumerate(raw["steps"])) if s]
    if not steps:
        _fault(path.name, "No usable steps in it.")
        return None
    try:
        order = int(raw.get("order", 500))
    except (TypeError, ValueError):
        order = 500
    return {
        "key": str(raw["key"]).strip(),
        "order": order,
        "title": str(raw["title"]).strip(),
        "industry": str(raw["industry"]).strip(),
        "blurb": str(raw["blurb"]).strip(),
        "asks": str(raw["asks"]).strip(),
        "sample": str(raw.get("sample") or ""),
        "steps": steps,
        "file": path.name,
    }


def _load_all():
    global _problems
    _problems = []
    found = {}
    if not STARTERS_DIR.is_dir():
        _fault(STARTERS_DIR.name,
               "The starters folder isn't there. The app still runs — you just "
               "start every sheet from nothing.")
        return []
    for path in sorted(STARTERS_DIR.glob("*.json")):
        s = _load_one(path)
        if s is None:
            continue
        if s["key"] in found:
            _fault(path.name, "Two files both call themselves %r. Kept the "
                              "first, ignored this one." % s["key"])
            continue
        found[s["key"]] = s
    return sorted(found.values(), key=lambda s: (s["order"], s["key"]))


def _all():
    global _cache
    if _cache is None:
        _cache = _load_all()
    return _cache


def reload():
    """Read the folder again. An edited starter shows up without a restart."""
    global _cache
    _cache = None
    return _all()


def problems():
    """What was wrong with the files, for the screen. Never a silent drop."""
    _all()
    return [dict(p) for p in _problems]


def list_starters():
    """The picker's shape — no steps, no sample text."""
    return [{
        "key": s["key"], "title": s["title"], "industry": s["industry"],
        "blurb": s["blurb"], "asks": s["asks"], "steps": len(s["steps"]),
    } for s in _all()]


def get_starter(key):
    """A full starter as a demo document, or None.

    Deep-copied on the way out. The cache is read by every request, and a
    caller that mutated it would change what the next prospect sees.
    """
    key = str(key or "").strip()
    for s in _all():
        if s["key"] == key:
            return {
                "name": s["title"],
                "client": "",
                "industry": s["industry"],
                "notes": "",
                "hourly_cost": 0.0,
                "starter": s["key"],
                "sample": s["sample"],
                "asks": s["asks"],
                "steps": [dict(step, handling=list(step["handling"]))
                          for step in s["steps"]],
            }
    return None
