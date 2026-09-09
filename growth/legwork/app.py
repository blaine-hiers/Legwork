"""Demo Generator — show an owner what could come off their plate, in the room.

Run it:  py app.py

Everything is local. Sheets live in `data/demos.db` next to this file. Nothing
pasted into the live demo goes anywhere — there is no network code in here at
all, and the smoke test enforces that for every app in this folder.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(next(p / "_shared" for p in Path(__file__).resolve().parents
                            if (p / "_shared" / "appkit.py").is_file())))

from appkit import App, HttpError                    # noqa: E402
from store import Store                              # noqa: E402

import core                                          # noqa: E402
import demo                                          # noqa: E402
import patterns                                      # noqa: E402
import starters                                      # noqa: E402

ROOT = Path(__file__).resolve().parent
app = App("Demo Generator", ROOT)
store = Store(ROOT / "data" / "demos.db")

# Stored the normal way — `Store` in a `data/*.db`, one collection — so
# `hub/export.py` writes these out to `../ai-context/` without knowing this app
# exists. The name becomes a heading in that dump, so it reads as English.
COLLECTION = "sheets"


# --------------------------------------------------------------- helpers

def _summary(doc):
    return {
        "id": doc.get("id"),
        "name": doc.get("name") or "Untitled",
        "client": doc.get("client") or "",
        "industry": doc.get("industry") or "",
        "steps": len(doc.get("steps") or []),
        "created": doc.get("created"),
        "updated": doc.get("updated"),
    }


def _load(sheet_id):
    doc = store.get(COLLECTION, sheet_id)
    if doc is None:
        raise HttpError(404, "That sheet isn't here any more.")
    return doc


def _with_analysis(doc):
    return {"sheet": doc, "analysis": core.analyze(doc)}


# ----------------------------------------------------------------- routes

@app.api("GET", "/api/state")
def state(req):
    """Everything the screen needs that never changes while it's open."""
    return {
        "starters": starters.list_starters(),
        # A starter file that failed to load goes on the screen, never into a
        # log. One that vanished quietly looks exactly like one nobody wrote.
        "starter_problems": starters.problems(),
        "handling": patterns.handling_choices(),
        "patterns": [{
            "id": p["id"], "answers": p["answers"], "title": p["title"],
            "becomes": p["becomes"], "needs": p["needs"], "why": p["why"],
            "share_low": int(round(p["low"] * 100)),
            "share_high": int(round(p["high"] * 100)),
            "effort": p["effort"], "risk": p["risk"], "demo": p.get("demo") or "",
        } for p in patterns.PATTERNS],
        "demos": [dict(v, key=k) for k, v in demo.DEMOS.items()],
        "documents": sorted(demo.DOCUMENT_TEMPLATES),
        "sheets": [_summary(d) for d in store.all(COLLECTION)],
    }


@app.api("GET", "/api/sheets")
def list_sheets(req):
    return {"sheets": [_summary(d) for d in store.all(COLLECTION)]}


@app.api("POST", "/api/sheets")
def create_sheet(req):
    body = req.body if isinstance(req.body, dict) else {}
    key = (body.get("starter") or "").strip()
    if key:
        seed = starters.get_starter(key)
        if seed is None:
            raise HttpError(404, "No starter called %r." % key)
        doc = core.normalize(seed)
        doc["starter"] = key
    else:
        doc = core.normalize(core.blank_demo())
    doc.pop("id", None)
    if body.get("client"):
        doc["client"] = str(body["client"]).strip()
    if body.get("name"):
        doc["name"] = str(body["name"]).strip()
    saved = store.save(COLLECTION, doc)
    return (201, _with_analysis(saved))


@app.api("GET", "/api/sheets/<sheet_id>")
def get_sheet(req):
    return _with_analysis(_load(req.params["sheet_id"]))


@app.api("PUT", "/api/sheets/<sheet_id>")
def save_sheet(req):
    sheet_id = req.params["sheet_id"]
    existing = _load(sheet_id)
    doc = core.normalize(req.json())
    doc["id"] = sheet_id
    for key in ("starter", "from_map"):
        if existing.get(key) and not doc.get(key):
            doc[key] = existing[key]
    return _with_analysis(store.save(COLLECTION, doc))


@app.api("DELETE", "/api/sheets/<sheet_id>")
def delete_sheet(req):
    sheet_id = req.params["sheet_id"]
    if not store.delete(COLLECTION, sheet_id):
        raise HttpError(404, "That sheet isn't here any more.")
    return {"deleted": sheet_id}


@app.api("POST", "/api/analyze")
def analyze_body(req):
    """Numbers for a sheet that has not been saved — the live recompute."""
    return {"analysis": core.analyze(req.json())}


@app.api("GET", "/api/starters/<key>")
def starter(req):
    seed = starters.get_starter(req.params["key"])
    if seed is None:
        raise HttpError(404, "No starter called %r." % req.params["key"])
    return {"starter": seed, "analysis": core.analyze(seed)}


# --------------------------------------------------- the live demo itself

@app.api("POST", "/api/demo/<key>")
def run_demo(req):
    body = req.body if isinstance(req.body, dict) else {}
    try:
        return {"key": req.params["key"], "result": demo.run(req.params["key"], body)}
    except KeyError as e:
        # KeyError stringifies with its own quotes round the message, which
        # reads as a bug on a screen an owner is looking at.
        raise HttpError(404, e.args[0] if e.args else str(e))
    except ValueError as e:
        raise HttpError(400, str(e))


# ------------------------------------------------ coming in from the mapper

@app.api("POST", "/api/import/flowmap")
def import_flowmap(req):
    """Read a `.flowmap.json` written by Workflow Mapper.

    A map drawn in the room becomes a sheet in the same room. What does *not*
    come across is what happens to the information — a map never recorded it,
    and inventing it would put ticks on a client's sheet the client never made.
    """
    body = req.body if isinstance(req.body, dict) else {}
    payload = body.get("handoff") if isinstance(body.get("handoff"), dict) else body
    try:
        doc = core.from_flowmap(payload)
    except ValueError as e:
        raise HttpError(400, str(e))
    if body.get("save"):
        doc.pop("id", None)
        doc = store.save(COLLECTION, doc)
    return _with_analysis(doc)


# ---------------------------------------------------------------- exports

_FORMATS = {
    "markdown": ("text/markdown", "md"),
    "text": ("text/plain", "txt"),
    "json": ("application/json", "json"),
}


def _export(doc, fmt):
    if fmt not in _FORMATS:
        raise HttpError(404, "I can't export %r. Try: %s."
                        % (fmt, ", ".join(sorted(_FORMATS))))
    doc = core.normalize(doc)
    analysis = core.analyze(doc)
    if fmt == "markdown":
        text = core.to_markdown(doc, analysis)
    elif fmt == "text":
        text = core.to_text(doc, analysis)
    else:
        text = json.dumps({"sheet": doc, "analysis": analysis}, indent=2,
                          ensure_ascii=False)
    mime, ext = _FORMATS[fmt]
    base = (doc.get("client") or doc.get("name") or "what-could-come-off").strip()
    safe = "".join(ch if (ch.isalnum() or ch in "-_ ") else " " for ch in base)
    safe = "-".join(safe.split()) or "what-could-come-off"
    if len(safe) > 60:                       # Windows gives up past 260 characters
        safe = safe[:60].rstrip("-") or "what-could-come-off"
    return {"format": fmt, "mime": mime, "filename": "%s.%s" % (safe, ext), "text": text}


@app.api("POST", "/api/export/<fmt>")
def export_body(req):
    return _export(req.json(), req.params["fmt"])


@app.api("GET", "/api/sheets/<sheet_id>/export/<fmt>")
def export_saved(req):
    return _export(_load(req.params["sheet_id"]), req.params["fmt"])


if __name__ == "__main__":
    app.run(verbose="-v" in sys.argv)
