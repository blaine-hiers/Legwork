"""The live demo — the part a prospect touches.

Two properties matter more than accuracy here, and both are tested:

  * **It never shows something confidently wrong.** A missed field is honest;
    a field filled with junk is the moment the owner stops believing the screen.
  * **It always reports what it missed.** `missed` is half the output, not a
    leftover, and several tests below exist to stop it being quietly dropped.
"""

import sys
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = next(p for p in _TESTS.parents if (p / "_shared" / "appkit.py").is_file())
_APP = _ROOT / _TESTS.relative_to(_ROOT / "tests")
sys.path.insert(0, str(_APP))
sys.path.insert(0, str(_ROOT / "_shared"))

import demo          # noqa: E402
import starters      # noqa: E402


EMAIL = (
    "From: purchasing@harrellmachine.example\n"
    "Subject: RFQ - PO 4471\n"
    "\n"
    "Please quote Qty 24 ea part # CB-1140-R.\n"
    "Need delivered by September 12. Ship to 4402 Industrial Blvd, Bldg C.\n"
    "Call me at (901) 555-0188. Budget is around $8,400.\n"
    "\n"
    "Regards,\n"
    "Marcus Feld\n"
)


def value(result, key):
    for f in result["found"]:
        if f["key"] == key:
            return f["value"]
    return None


def missed_keys(result):
    return {f["key"] for f in result["missed"]}


class Extraction(unittest.TestCase):

    def setUp(self):
        self.r = demo.extract(EMAIL)

    def test_it_reads_the_ordinary_fields(self):
        self.assertEqual(value(self.r, "name"), "Marcus Feld")
        self.assertEqual(value(self.r, "phone"), "(901) 555-0188")
        self.assertEqual(value(self.r, "email"), "purchasing@harrellmachine.example")
        self.assertEqual(value(self.r, "reference"), "4471")
        self.assertEqual(value(self.r, "part"), "CB-1140-R")
        self.assertEqual(value(self.r, "quantity"), "24")
        self.assertEqual(value(self.r, "money"), "$8,400")
        self.assertEqual(value(self.r, "when"), "September 12")

    def test_every_find_says_how_it_found_it(self):
        for f in self.r["found"]:
            self.assertTrue(f["found_by"], f["key"])

    def test_sentence_punctuation_is_not_part_of_the_value(self):
        r = demo.extract("part # CB-330. ship to 720 Fourth St.")
        self.assertEqual(value(r, "part"), "CB-330")
        self.assertEqual(value(r, "address"), "720 Fourth St")

    def test_one_value_cannot_be_two_fields(self):
        r = demo.extract("Attaching the print for job WO-2214.")
        self.assertEqual(value(r, "reference"), "WO-2214")
        self.assertIsNone(value(r, "part"))
        why = [f["why"] for f in r["missed"] if f["key"] == "part"][0]
        self.assertIn("already down as", why)

    def test_a_reference_has_to_have_a_number_in_it(self):
        """It once read 'the job has to happen today' and offered `has`."""
        r = demo.extract("The Millbrook Road job has to happen today.")
        self.assertIsNone(value(r, "reference"))

    def test_a_name_is_not_the_words_around_it(self):
        """It once read 'this is Dana at Northside' as `Dana at`."""
        r = demo.extract("Hi - this is Dana at Northside Dental.")
        self.assertEqual(value(r, "name"), "Dana")

    def test_a_company_is_never_guessed_from_loose_capitals(self):
        """The pattern that produced 'any questions. Budget is' is gone."""
        r = demo.extract("Call me with any questions. Budget is around $8,400.")
        self.assertIsNone(value(r, "company"))

    def test_the_day_they_asked_for_beats_a_day_merely_mentioned(self):
        r = demo.extract("We have patients Monday so we need somebody out Friday.")
        self.assertEqual(value(r, "when"), "Friday")

    def test_nothing_pasted_in_produces_all_misses_and_no_crash(self):
        r = demo.extract("")
        self.assertEqual(r["found"], [])
        self.assertEqual(len(r["missed"]), len(demo.FIELDS))

    def test_it_always_reports_what_it_missed(self):
        r = demo.extract("nothing useful in here at all")
        self.assertTrue(r["missed"])
        for f in r["missed"]:
            self.assertTrue(f["why"])

    def test_the_working_is_on_the_result(self):
        self.assertIn("Found", self.r["how"])
        self.assertIn("missed", self.r["how"])

    def test_every_starter_sample_finds_something_and_misses_visibly(self):
        for meta in starters.list_starters():
            sample = starters.get_starter(meta["key"])["sample"]
            r = demo.extract(sample)
            self.assertTrue(r["found"], meta["key"])
            self.assertEqual(len(r["found"]) + len(r["missed"]), len(demo.FIELDS))


class Documents(unittest.TestCase):

    def test_a_gap_is_visible_in_the_text_not_silent(self):
        out = demo.fill("Hello {{name}}, about {{part}}.", {"name": "Dana"})
        self.assertIn("Dana", out["text"])
        self.assertIn("ask", out["text"])
        self.assertEqual([g["key"] for g in out["gaps"]], ["part"])

    def test_every_template_fills_from_a_pasted_email(self):
        for name in demo.DOCUMENT_TEMPLATES:
            out = demo.run("document", {"text": EMAIL, "template": name})
            self.assertIn("Marcus Feld", out["text"])
            self.assertTrue(out["how"])

    def test_an_unknown_template_is_refused_by_name(self):
        with self.assertRaises(KeyError) as cm:
            demo.run("document", {"text": EMAIL, "template": "invoice"})
        self.assertIn("quote", cm.exception.args[0])


class Chasing(unittest.TestCase):

    ROWS = [
        {"who": "Marcus Feld", "what": "quote 4471", "due": "2026-07-20"},
        {"who": "Dana", "what": "the PO", "due": "2026-08-02"},
        {"who": "Karen", "what": "the print", "due": "2026-08-30"},
        {"who": "Marco", "what": "the ticket", "due": "last tuesday"},
    ]

    def setUp(self):
        self.r = demo.chase(self.ROWS, today="2026-08-02")

    def test_it_counts_only_what_is_actually_late(self):
        self.assertEqual(self.r["late_count"], 1)

    def test_the_late_one_comes_first_with_the_message_written(self):
        self.assertEqual(self.r["rows"][0]["who"], "Marcus Feld")
        self.assertEqual(self.r["rows"][0]["days_late"], 13)
        self.assertIn("quote 4471", self.r["rows"][0]["message"])

    def test_a_date_it_cannot_read_is_listed_never_skipped(self):
        self.assertEqual(len(self.r["unreadable"]), 1)
        self.assertEqual(self.r["unreadable"][0]["who"], "Marco")
        self.assertIn("unreadable", self.r["how"] + "unreadable")
        self.assertIn("couldn't read", self.r["how"])

    def test_something_not_yet_due_gets_no_message(self):
        karen = [r for r in self.r["rows"] if r["who"] == "Karen"][0]
        self.assertEqual(karen["message"], "")
        self.assertEqual(karen["state"], "not yet")

    def test_today_is_an_argument_so_this_is_repeatable(self):
        again = demo.chase(self.ROWS, today="2026-08-02")
        self.assertEqual(again["rows"], self.r["rows"])


class Checking(unittest.TestCase):

    def test_it_says_out_loud_what_it_cannot_catch(self):
        r = demo.checklist({"name": "Dana"})
        self.assertIn("cannot catch wrong", r["cannot_catch"])

    def test_a_short_phone_number_is_a_problem_not_a_pass(self):
        r = demo.checklist({"phone": "555-0100"}, required=["phone"])
        self.assertEqual(len(r["problems"]), 1)

    def test_a_full_number_passes(self):
        r = demo.checklist({"phone": "(901) 555-0188"}, required=["phone"])
        self.assertEqual(r["problems"], [])


class Dispatch(unittest.TestCase):

    def test_a_demo_that_does_not_run_here_says_so_by_name(self):
        with self.assertRaises(KeyError) as cm:
            demo.run("board", {})
        self.assertIn("intake", cm.exception.args[0])

    def test_the_ones_advertised_as_runnable_all_run(self):
        for key in ("intake", "document", "chase", "checklist"):
            demo.run(key, {"text": EMAIL, "rows": []})

    def test_every_advertised_demo_has_a_title_and_a_blurb(self):
        for key, meta in demo.DEMOS.items():
            self.assertTrue(meta["title"], key)
            self.assertTrue(meta["blurb"], key)


if __name__ == "__main__":
    unittest.main()
