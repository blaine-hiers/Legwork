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

    def test_the_tenth_edit_in_a_row_lands_exactly_like_the_first(self):
        """One save per sheet is not the shape of the conversation this serves.

        The numbers change for as long as the owner is talking, so the tenth
        one typed has to reach the disk on the same terms as the first.
        """
        _, r = call("POST", "/api/sheets", {"starter": "scheduling"})
        sheet = r["sheet"]
        sid = sheet["id"]
        for n in range(1, 11):
            sheet["steps"][0]["minutes"] = n
            sheet["client"] = "Client %d" % n
            code, saved = call("PUT", "/api/sheets/" + sid, sheet)
            self.assertEqual(code, 200, "edit %d" % n)
            self.assertEqual(saved["sheet"]["steps"][0]["minutes"], n)
            _, back = call("GET", "/api/sheets/" + sid)
            self.assertEqual(back["sheet"]["steps"][0]["minutes"], n, "edit %d" % n)
            self.assertEqual(back["sheet"]["client"], "Client %d" % n)

    def test_a_step_nobody_touched_yet_still_saves_after_ten_others_did(self):
        _, r = call("POST", "/api/sheets", {"starter": "field-paperwork"})
        sheet = r["sheet"]
        sid = sheet["id"]
        self.assertGreater(len(sheet["steps"]), 1, "this starter needs two steps")
        for n in range(1, 11):
            sheet["steps"][0]["runs_per_month"] = n
            call("PUT", "/api/sheets/" + sid, sheet)
        sheet["steps"][-1]["minutes"] = 45
        call("PUT", "/api/sheets/" + sid, sheet)
        _, back = call("GET", "/api/sheets/" + sid)
        self.assertEqual(back["sheet"]["steps"][-1]["minutes"], 45)
        self.assertEqual(back["sheet"]["steps"][0]["runs_per_month"], 10)

    def test_a_saved_sheet_keeps_which_starter_it_came_from(self):
        _, r = call("POST", "/api/sheets", {"starter": "machine-shop-job"})
        sheet = dict(r["sheet"])
        sheet.pop("starter", None)
        _, saved = call("PUT", "/api/sheets/" + sheet["id"], sheet)
        self.assertEqual(saved["sheet"]["starter"], "machine-shop-job")

    def test_role_rates_round_trip_through_save_and_feed_the_analysis(self):
        """`role_rates` has no input on the screen -- it arrives by JSON/
        import -- but a save must still keep it, and `by_role` must price
        that role at it, not at the sheet's blended rate."""
        _, r = call("POST", "/api/sheets", {"starter": "scheduling"})
        sheet = r["sheet"]
        sheet["hourly_cost"] = 22
        sheet["role_rates"] = {"Technician": 95}
        for step in sheet["steps"]:
            step["who"] = "Technician"
            step["runs_per_month"] = 20
        code, saved = call("PUT", "/api/sheets/" + sheet["id"], sheet)
        self.assertEqual(code, 200)
        self.assertEqual(saved["sheet"]["role_rates"], {"Technician": 95})
        by_who = {row["who"]: row for row in saved["analysis"]["by_role"]}
        self.assertTrue(by_who["Technician"]["has_own_rate"])
        self.assertIn("$95", by_who["Technician"]["money_how"])
        _, back = call("GET", "/api/sheets/" + sheet["id"])
        self.assertEqual(back["sheet"]["role_rates"], {"Technician": 95})

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


class TheSaveLoop(unittest.TestCase):
    """The screen's half of saving, which is where it broke.

    Every input on a step is wired straight to the step object it edits, so the
    handlers hold references *into* the object graph the page was painted from.
    Replacing that graph with the copy the server sends back unhooks all of
    them at once: the inputs keep working, and nothing they write is ever read
    again. There is no JavaScript runtime in this suite, so the rule is checked
    twice over -- read out of `app.js`, and replayed over real HTTP with the
    same reference held the same way.
    """

    JS = (_APP / "static" / "app.js").read_text(encoding="utf-8")
    HTML = (_APP / "static" / "index.html").read_text(encoding="utf-8")

    # What a person types, and therefore what the page must never take back
    # from a response. Kept in step with `app.js` by the test below it.
    TYPED = {"name", "client", "industry", "notes", "hourly_cost", "steps"}

    def body_of(self, name):
        """The source of one top-level function in `app.js`."""
        start = self.JS.index("function %s(" % name)
        end = self.JS.index("\n  }\n", start)
        return self.JS[start:end]

    def test_a_save_does_not_swap_the_object_the_inputs_are_wired_to(self):
        body = self.body_of("doSave")
        self.assertNotIn("S.sheet =", body,
                         "the save handler is rebinding the open sheet again")
        self.assertIn("adoptSaved", body)

    def test_a_save_does_not_rebuild_the_fields_under_the_person_typing(self):
        body = self.body_of("doSave")
        for repaint in ("paintSteps(", "paintSheet("):
            self.assertNotIn(repaint, body,
                             "repainting on save takes the caret with it")

    def test_the_page_and_this_test_agree_on_what_a_person_types(self):
        listed = re.search(r"var TYPED = \{([^}]*)\}", self.JS)
        self.assertTrue(listed, "app.js no longer declares TYPED")
        keys = set(re.findall(r"(\w+):", listed.group(1)))
        self.assertEqual(keys, self.TYPED)

    def test_the_status_pill_either_reports_or_is_not_there(self):
        """It must not sit in the header implying feedback that never comes."""
        # assertTrue, not assertIn: a failure here would otherwise print the
        # whole of app.js and bury the one line that says what is wrong.
        if 'id="saveStatus"' in self.HTML:
            self.assertTrue('$("#saveStatus")' in self.JS,
                            "the markup has a save pill that nothing ever paints")
        self.assertFalse("UI.autosave(doSave, null)" in self.JS,
                         "autosave is being built with no status element again")

    def test_a_second_edit_reaches_the_stored_document(self):
        """The screen's loop, replayed: edit, save, edit again, save."""
        _, r = call("POST", "/api/sheets", {"starter": "hvac-service-call"})
        sheet = r["sheet"]
        sid = sheet["id"]
        step = sheet["steps"][0]           # what the field handler closes over

        def typed_then_saved(minutes):
            step["minutes"] = minutes      # oninput
            _, reply = call("PUT", "/api/sheets/" + sid, sheet)
            for key, value in reply["sheet"].items():        # adoptSaved
                if key not in self.TYPED:
                    sheet[key] = value
            return reply

        typed_then_saved(11)
        reply = typed_then_saved(22)

        # The handler is still wired to the sheet that gets sent.
        self.assertIs(step, sheet["steps"][0])
        # And the hazard is real: the reply's steps are different objects, so
        # taking them would have left the handler holding an orphan.
        self.assertIsNot(step, reply["sheet"]["steps"][0])

        _, back = call("GET", "/api/sheets/" + sid)
        self.assertEqual(back["sheet"]["steps"][0]["minutes"], 22)

    def test_what_comes_back_never_overwrites_what_is_still_being_typed(self):
        """A reply is older than the screen by the length of the round trip."""
        _, r = call("POST", "/api/sheets", {"starter": "distributor-quote"})
        sheet = r["sheet"]
        sheet["client"] = "Northgate Mechanical"
        _, reply = call("PUT", "/api/sheets/" + sheet["id"], sheet)
        sheet["client"] = "Northgate Mechanical Ltd"        # typed in flight
        for key, value in reply["sheet"].items():           # adoptSaved
            if key not in self.TYPED:
                sheet[key] = value
        self.assertEqual(sheet["client"], "Northgate Mechanical Ltd")
        self.assertEqual(sheet["id"], reply["sheet"]["id"])
        self.assertEqual(sheet.get("starter"), "distributor-quote")

    def test_open_flushes_the_pending_save_before_swapping_the_sheet(self):
        """#13: `save.now()` must run, and run before `S.sheet` is replaced,
        or the debounced write lands on the wrong sheet once it fires."""
        body = self.body_of("open")
        self.assertIn("save.now()", body)
        self.assertLess(body.index("save.now()"), body.index("S.sheet = r.sheet"),
                        "save.now() must flush before the sheet is replaced")

    def test_an_edit_just_before_switching_sheets_is_not_lost(self):
        """The debounce timer fires after the switch; `open()`'s save.now()
        is what's supposed to have already flushed it by then."""
        _, a = call("POST", "/api/sheets", {"starter": "hvac-service-call"})
        sheet_a = a["sheet"]
        sheet_a["client"] = "Edited just before switching"   # oninput
        # open(otherId): save.now() flushing the sheet that's still open ...
        _, saved = call("PUT", "/api/sheets/" + sheet_a["id"], sheet_a)
        for key, value in saved["sheet"].items():             # adoptSaved
            if key not in self.TYPED:
                sheet_a[key] = value
        # ... then the switch itself completes.
        _, b = call("POST", "/api/sheets", {"starter": "distributor-quote"})

        _, back = call("GET", "/api/sheets/" + sheet_a["id"])
        self.assertEqual(back["sheet"]["client"], "Edited just before switching")
        self.assertNotEqual(b["sheet"]["id"], sheet_a["id"])


class RecomputeGuard(unittest.TestCase):
    """#14: a stale `/api/analyze` reply must not repaint the totals panel
    after switching sheets. `/api/analyze` echoes back no sheet id to check
    the way a save reply does, so `recompute` has to stamp the id itself at
    issue time and check it at reply time — the same rule as `adoptSaved`,
    just carried by a closure variable instead of the response body. No JS
    runtime here to actually race the two requests, so the guard is checked
    structurally, the way `TheSaveLoop` checks `open`'s save.now() above.
    """

    JS = (_APP / "static" / "app.js").read_text(encoding="utf-8")

    def body_of_recompute(self):
        start = self.JS.index("var recompute = UI.debounce(function () {")
        end = self.JS.index("}, 220);", start)
        return self.JS[start:end]

    def test_the_sheet_id_is_stamped_before_the_request_and_checked_before_painting(self):
        body = self.body_of_recompute()
        self.assertIn("var issuedFor = S.sheet.id;", body)
        self.assertIn("paintAnalysis(", body)
        stamp = body.index("var issuedFor = S.sheet.id;")
        request = body.index("api.post(")
        check = body.index("S.sheet.id === issuedFor")
        paint = body.index("paintAnalysis(")
        self.assertLess(stamp, request,
                        "the id must be captured before the request is sent")
        self.assertLess(check, paint,
                        "the id must be checked before the reply is painted")

    def test_the_guard_is_shaped_like_adoptSaved_not_a_second_mechanism(self):
        body = self.body_of_recompute()
        self.assertIn("S.sheet.id ===", body)
        save_body = self.JS[self.JS.index("function adoptSaved("):
                             self.JS.index("function adoptSaved(") + 400]
        self.assertIn("S.sheet.id", save_body)


class ChaseParsing(unittest.TestCase):
    """`parseChase` in app.js, checked the same way `TheSaveLoop` checks the
    save loop: no JS runtime in this suite, so the algorithm is mirrored in
    Python and driven over the real `/api/demo/chase` endpoint, and the JS
    source is checked structurally to keep the two in step.
    """

    JS = (_APP / "static" / "app.js").read_text(encoding="utf-8")

    @staticmethod
    def parse_chase(text):
        """Mirrors app.js's parseChase() exactly. Kept in step by the
        structural test below."""
        rows = []
        for line in str(text or "").split("\n"):
            if not line.strip():
                continue
            bits = line.split(",")
            if len(bits) < 2:
                rows.append({"who": line.strip(), "what": "", "due": ""})
                continue
            rows.append({
                "who": bits[0].strip(),
                "what": ",".join(bits[1:-1]).strip(),
                "due": bits[-1].strip(),
            })
        return rows

    def body_of(self, name):
        start = self.JS.index("function %s(" % name)
        end = self.JS.index("\n  }\n", start)
        return self.JS[start:end]

    def test_the_page_and_this_test_agree_on_when_a_line_is_dropped(self):
        body = self.body_of("parseChase")
        self.assertIn("if (!line.trim()) return null", body)
        self.assertNotIn("bits.length < 2 || !line.trim()", body,
                         "a no-comma line is being dropped again")

    def test_a_no_comma_line_is_listed_not_dropped(self):
        rows = self.parse_chase(
            "Marcus Feld,quote 4471,2026-07-20\njust some garbled paste\n")
        self.assertEqual(len(rows), 2)
        code, r = call("POST", "/api/demo/chase",
                       {"rows": rows, "today": "2026-08-02"})
        self.assertEqual(code, 200)
        result = r["result"]
        self.assertEqual(len(result["unreadable"]), 1)
        self.assertEqual(result["unreadable"][0]["who"], "just some garbled paste")

    def test_a_no_comma_line_gets_an_honest_reason_not_a_date_complaint(self):
        """It has no date at all to complain about — the real problem is
        that there was nothing to split a name and a date out of."""
        rows = self.parse_chase("just some garbled paste\n")
        code, r = call("POST", "/api/demo/chase",
                       {"rows": rows, "today": "2026-08-02"})
        why = r["result"]["unreadable"][0]["why"]
        self.assertIn("comma", why)
        self.assertNotIn("2026-08-14", why)     # the date-format complaint

    def test_a_blank_line_is_ignored_silently(self):
        rows = self.parse_chase("Marcus Feld,quote 4471,2026-07-20\n\n\n")
        self.assertEqual(len(rows), 1)

    def test_the_shown_count_reflects_everything_pasted_not_just_what_parsed(self):
        """The specific harm the issue names: '2 things checked' when 3 lines
        were pasted reads as confirmation that all the input was seen."""
        pasted = ("Marcus Feld,quote 4471,2026-07-20\n"
                   "Dana,the PO,2026-08-02\n"
                   "no comma here\n"
                   "\n")
        rows = self.parse_chase(pasted)
        self.assertEqual(len(rows), 3)     # only the blank line is dropped
        code, r = call("POST", "/api/demo/chase",
                       {"rows": rows, "today": "2026-08-02"})
        result = r["result"]
        self.assertEqual(len(result["rows"]) + len(result["unreadable"]), 3)
        self.assertIn("3 things checked", result["how"])


class PromiseChains(unittest.TestCase):
    """Every `UI.guard(...)` chain in app.js must end in its own `.catch()`.

    `guard()` already toasts the error and rethrows (see `_shared/ui.js`), so
    a chain fired from a UI event handler with no further `.then()`/`.catch()`
    downstream leaves that rethrow with nowhere to land: an unhandled promise
    rejection, console noise with no user-visible effect since the toast
    already ran. There is no JS runtime in this suite to actually trigger a
    rejection and watch it stay unhandled, so this is checked the way the
    rest of app.js is checked here: structurally, against the source text.
    """

    JS = (_APP / "static" / "app.js").read_text(encoding="utf-8")

    def test_every_guard_chain_swallows_its_own_rethrow(self):
        guards = self.JS.count("UI.guard(")
        self.assertGreater(guards, 0, "UI.guard( no longer appears in app.js")
        swallowed = self.JS.count("guard already toasted; nothing else to do")
        self.assertEqual(swallowed, guards,
                         "a UI.guard(...) chain is missing its terminal .catch()")

    def test_importing_a_wrong_shaped_file_is_still_a_clean_400(self):
        """The user-facing side of #6: unchanged. `guard()` still gets a
        rejection to toast; only the unhandled-rejection noise is new here."""
        code, r = call("POST", "/api/import/flowmap", {"handoff": {"format": "x"}})
        self.assertEqual(code, 400)
        self.assertIn("error", r)


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
