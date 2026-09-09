"""Every endpoint, over real HTTP, against a throwaway database.

Same arrangement as the mapper's suite: the store is pointed at a temp file
before `app.py` builds one, so nothing here can touch a real prospect's sheet.
"""

import json
import re
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = next(p for p in _TESTS.parents if (p / "_shared" / "appkit.py").is_file())
_APP = _ROOT / _TESTS.relative_to(_ROOT / "tests")
sys.path.insert(0, str(_APP))
sys.path.insert(0, str(_ROOT / "_shared"))

_TMP = tempfile.mkdtemp(prefix="demogen-test-")

import store as _store          # noqa: E402
_real_store = _store.Store


class _TempStore(_real_store):
    def __init__(self, path):
        _real_store.__init__(self, os.path.join(_TMP, "test-demos.db"))


_store.Store = _TempStore

import app as appmod            # noqa: E402

_store.Store = _real_store

BASE = None
SERVER = None


def setUpModule():
    global BASE, SERVER
    SERVER, BASE = appmod.app.serve_background()


def tearDownModule():
    if SERVER:
        SERVER.shutdown()
        SERVER.server_close()
    shutil.rmtree(_TMP, ignore_errors=True)


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class State(unittest.TestCase):

    def test_the_screen_gets_everything_it_needs_in_one_call(self):
        code, s = call("GET", "/api/state")
        self.assertEqual(code, 200)
        for key in ("starters", "handling", "patterns", "demos", "documents", "sheets"):
            self.assertIn(key, s)
            self.assertTrue(s[key] or key == "sheets", key)

    def test_every_answer_on_screen_has_a_pattern_behind_it(self):
        _, s = call("GET", "/api/state")
        answered = {p["answers"] for p in s["patterns"]}
        self.assertEqual({h["key"] for h in s["handling"]}, answered)

    def test_no_pattern_is_advertised_as_a_single_figure(self):
        _, s = call("GET", "/api/state")
        for p in s["patterns"]:
            self.assertGreater(p["share_high"], p["share_low"], p["id"])


class Sheets(unittest.TestCase):

    def test_a_sheet_from_a_starter_arrives_with_its_steps(self):
        code, r = call("POST", "/api/sheets", {"starter": "hvac-service-call",
                                               "client": "Northgate Mechanical"})
        self.assertEqual(code, 201)
        self.assertEqual(r["sheet"]["client"], "Northgate Mechanical")
        self.assertTrue(r["sheet"]["steps"])
        self.assertIn("analysis", r)

    def test_a_starter_sheet_claims_nothing_until_volumes_are_answered(self):
        _, r = call("POST", "/api/sheets", {"starter": "distributor-quote"})
        self.assertEqual(r["analysis"]["totals"]["saved_high"], 0)
        self.assertTrue(any("how often" in w for w in r["analysis"]["warnings"]))

    def test_an_unknown_starter_is_a_clean_404(self):
        code, r = call("POST", "/api/sheets", {"starter": "nope"})
        self.assertEqual(code, 404)
        self.assertIn("error", r)

    def test_saving_recomputes_and_the_numbers_come_back(self):
        _, r = call("POST", "/api/sheets", {"starter": "scheduling"})
        sheet = r["sheet"]
        for step in sheet["steps"]:
            step["runs_per_month"] = 20
        code, saved = call("PUT", "/api/sheets/" + sheet["id"], sheet)
        self.assertEqual(code, 200)
        self.assertGreater(saved["analysis"]["totals"]["saved_high"], 0)
        self.assertGreater(saved["analysis"]["totals"]["saved_high"],
                           saved["analysis"]["totals"]["saved_low"])

    def test_a_saved_sheet_keeps_which_starter_it_came_from(self):
        _, r = call("POST", "/api/sheets", {"starter": "machine-shop-job"})
        sheet = dict(r["sheet"])
        sheet.pop("starter", None)
        _, saved = call("PUT", "/api/sheets/" + sheet["id"], sheet)
        self.assertEqual(saved["sheet"]["starter"], "machine-shop-job")

    def test_deleting_twice_is_a_404_not_a_silent_success(self):
        _, r = call("POST", "/api/sheets", {})
        sid = r["sheet"]["id"]
        self.assertEqual(call("DELETE", "/api/sheets/" + sid)[0], 200)
        self.assertEqual(call("DELETE", "/api/sheets/" + sid)[0], 404)

    def test_a_missing_sheet_is_a_404(self):
        self.assertEqual(call("GET", "/api/sheets/nothere")[0], 404)

    def test_analyze_works_on_a_sheet_that_was_never_saved(self):
        code, r = call("POST", "/api/analyze", {
            "steps": [{"name": "Type it in", "minutes": 20, "runs_per_month": 30,
                       "handling": ["retyped"]}]})
        self.assertEqual(code, 200)
        self.assertGreater(r["analysis"]["totals"]["saved_high"],
                           r["analysis"]["totals"]["saved_low"])


class TheLiveDemo(unittest.TestCase):

    EMAIL = ("Hi, this is Dana at Northside Dental. Model RTU-4400-B, we need "
             "somebody out Friday. 229-555-0142. PO 88213.")

    def test_intake_returns_what_it_found_and_what_it_missed(self):
        code, r = call("POST", "/api/demo/intake", {"text": self.EMAIL})
        self.assertEqual(code, 200)
        self.assertTrue(r["result"]["found"])
        self.assertIn("missed", r["result"])

    def test_a_document_comes_back_written(self):
        code, r = call("POST", "/api/demo/document",
                       {"text": self.EMAIL, "template": "work-order"})
        self.assertEqual(code, 200)
        self.assertIn("WORK ORDER", r["result"]["text"])
        self.assertIn("Dana", r["result"]["text"])

    def test_an_unknown_demo_is_a_clean_404_with_no_python_quoting(self):
        code, r = call("POST", "/api/demo/teleport", {})
        self.assertEqual(code, 404)
        self.assertFalse(r["error"].startswith('"'))
        self.assertIn("intake", r["error"])

    def test_chase_needs_no_text_and_pins_its_own_today(self):
        code, r = call("POST", "/api/demo/chase", {
            "rows": [{"who": "A", "what": "x", "due": "2026-01-01"}],
            "today": "2026-08-02"})
        self.assertEqual(code, 200)
        self.assertEqual(r["result"]["late_count"], 1)

    def test_a_junk_body_does_not_500(self):
        code, _ = call("POST", "/api/demo/intake", {"text": None})
        self.assertEqual(code, 200)


class ImportingAMap(unittest.TestCase):

    HANDOFF = {
        "format": "flowmap-handoff", "v": 1,
        "source": {"name": "Quote to cash", "client": "Northgate Mechanical",
                   "industry": "HVAC", "map_id": "m1"},
        "map": {"steps": [{"id": "s1", "name": "Type it in", "role": "Office",
                           "touch_min": 12}]},
    }

    def test_a_map_becomes_a_sheet(self):
        code, r = call("POST", "/api/import/flowmap",
                       {"handoff": self.HANDOFF, "save": True})
        self.assertEqual(code, 200)
        self.assertEqual(r["sheet"]["client"], "Northgate Mechanical")
        self.assertTrue(r["sheet"]["id"])

    def test_the_ticks_are_not_invented_on_the_way_in(self):
        _, r = call("POST", "/api/import/flowmap", {"handoff": self.HANDOFF})
        for step in r["sheet"]["steps"]:
            self.assertEqual(step["handling"], [])
        self.assertEqual(r["analysis"]["totals"]["saved_high"], 0)

    def test_a_newer_map_is_refused_with_a_readable_400(self):
        bad = dict(self.HANDOFF, v=99)
        code, r = call("POST", "/api/import/flowmap", {"handoff": bad})
        self.assertEqual(code, 400)
        self.assertIn("newer Workflow Mapper", r["error"])

    def test_the_wrong_file_is_refused(self):
        code, _ = call("POST", "/api/import/flowmap", {"handoff": {"format": "x"}})
        self.assertEqual(code, 400)


class Exports(unittest.TestCase):

    def sheet(self):
        _, r = call("POST", "/api/sheets", {"starter": "hvac-service-call",
                                            "client": "Northgate Mechanical"})
        s = r["sheet"]
        for step in s["steps"]:
            step["runs_per_month"] = 15
        call("PUT", "/api/sheets/" + s["id"], s)
        return s["id"]

    def test_every_format_comes_back_with_a_filename(self):
        sid = self.sheet()
        for fmt in ("markdown", "text", "json"):
            code, r = call("GET", "/api/sheets/%s/export/%s" % (sid, fmt))
            self.assertEqual(code, 200, fmt)
            self.assertTrue(r["text"])
            self.assertTrue(r["filename"].startswith("Northgate-Mechanical"), r["filename"])

    def test_the_one_pager_never_states_a_single_point_saving(self):
        sid = self.sheet()
        _, r = call("GET", "/api/sheets/%s/export/markdown" % sid)
        head = r["text"].split("## Everything you described")[0]
        self.assertIn("–", head)
        for banned in ("guarantee", "will save you", "ROI of"):
            self.assertNotIn(banned, r["text"])

    def test_an_unknown_format_is_a_404_that_lists_the_real_ones(self):
        code, r = call("GET", "/api/sheets/%s/export/pdf" % self.sheet())
        self.assertEqual(code, 404)
        self.assertIn("markdown", r["error"])


class TheShell(unittest.TestCase):
    """The half of the rule that breaks quietly — see `system/apps/CLAUDE.md`."""

    def test_the_page_asks_for_shared_files_at_exactly_two_absolute_paths(self):
        html = (_APP / "static" / "index.html").read_text(encoding="utf-8")
        absolute = set(re.findall(r'(?:href|src)="(/[^"]*)"', html))
        self.assertTrue(absolute <= {"/_shared/base.css", "/_shared/ui.js"},
                        "a third absolute path will break under the phone shell: "
                        + repr(absolute))

    def test_the_front_end_never_fetches_its_own_api_directly(self):
        js = (_APP / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('fetch("/api', js)
        self.assertNotIn("fetch('/api", js)


if __name__ == "__main__":
    unittest.main()
