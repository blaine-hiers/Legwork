"""The arithmetic, and the rule it exists to hold.

The headline test in here is `test_no_step_can_ever_report_a_single_figure`.
`05` §8 forbids a single-point figure on a client's page, and this app is the
one that puts figures in front of a prospect before anybody has been paid. Every
other test here is support for that one.
"""

import sys
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = next(p for p in _TESTS.parents if (p / "_shared" / "appkit.py").is_file())
_APP = _ROOT / _TESTS.relative_to(_ROOT / "tests")
sys.path.insert(0, str(_APP))
sys.path.insert(0, str(_ROOT / "_shared"))

import core          # noqa: E402
import patterns      # noqa: E402
import starters      # noqa: E402


def sheet(*handling_per_step, **kw):
    """A sheet whose steps each take 30 minutes, 10 times a month."""
    return {
        "name": "Test",
        "client": kw.get("client", "A Company"),
        "hourly_cost": kw.get("hourly_cost", 0),
        "steps": [{
            "id": "s%d" % (i + 1), "name": "Step %d" % (i + 1),
            "minutes": kw.get("minutes", 30),
            "runs_per_month": kw.get("runs", 10),
            "handling": list(h),
        } for i, h in enumerate(handling_per_step)],
    }


class TheRangeRule(unittest.TestCase):

    def test_no_step_can_ever_report_a_single_figure(self):
        """Every combination of answers, on a step big enough to round apart."""
        keys = [h["key"] for h in patterns.HANDLING]
        combos = []
        for a in keys:
            combos.append([a])
            for b in keys:
                if a != b:
                    combos.append([a, b])
        combos.append(keys)                       # every box ticked at once
        doc = sheet(*combos, minutes=120, runs=40)
        a = core.analyze(doc)
        for row in a["steps"]:
            self.assertTrue(row["patterns"], row["name"])
            self.assertGreater(row["share_high"], row["share_low"],
                               "%s collapsed to one figure" % row["name"])
            self.assertGreater(row["saved_high"], row["saved_low"], row["name"])

    def test_two_heavy_patterns_do_not_add_past_the_step(self):
        """The bug this model replaced: 0.85 + 0.80 capped to 1.0 and 1.0."""
        a = core.analyze(sheet(["written", "looked-up"]))
        row = a["steps"][0]
        self.assertLess(row["share_high"], 100)
        self.assertGreater(row["share_high"], row["share_low"])
        self.assertLessEqual(row["saved_high"], row["hours_month"])

    def test_nothing_ever_reaches_a_hundred_per_cent(self):
        every = [h["key"] for h in patterns.HANDLING]
        row = core.analyze(sheet(every))["steps"][0]
        self.assertLessEqual(row["share_high"], int(core.STEP_CEILING * 100))

    def test_the_model_guard_actually_fires(self):
        """If someone later replaces `_compose` with a sum and a clamp."""
        original = core._compose
        try:
            core._compose = lambda fracs: 1.0        # every band flattens
            with self.assertRaises(patterns.SavingsError):
                core.analyze(sheet(["retyped"]))
        finally:
            core._compose = original


class TheJudgementPattern(unittest.TestCase):

    def test_a_judgement_call_stays_with_the_person(self):
        row = core.analyze(sheet(["decided"]))["steps"][0]
        self.assertLess(row["share_high"], 25,
                        "the one pattern that says no has started saying yes")

    def test_it_is_the_smallest_claim_in_the_library(self):
        highs = {p["id"]: p["high"] for p in patterns.PATTERNS}
        self.assertEqual(min(highs, key=highs.get), "judgement")


class Arithmetic(unittest.TestCase):

    def test_every_figure_carries_its_working(self):
        a = core.analyze(sheet(["retyped"], ["chased"]))
        self.assertIn("×", a["totals"]["how"] + a["steps"][0]["hours_how"])
        for row in a["steps"]:
            self.assertTrue(row["hours_how"])
            self.assertTrue(row["saved_how"])
            self.assertTrue(row["priority_how"])

    def test_priority_is_the_formula_from_05(self):
        row = core.analyze(sheet(["chased"]))["steps"][0]
        self.assertEqual(row["priority"],
                         row["impact"] * 2 - row["effort"] - row["risk"])
        self.assertIn("× 2", row["priority_how"])

    def test_a_step_nobody_answered_claims_nothing(self):
        row = core.analyze(sheet([]))["steps"][0]
        self.assertEqual((row["saved_low"], row["saved_high"]), (0, 0))
        self.assertEqual(row["patterns"], [])
        self.assertIn("nothing is claimed", row["saved_how"])

    def test_zero_volume_claims_nothing_and_says_so(self):
        a = core.analyze(sheet(["retyped"], runs=0))
        self.assertEqual(a["totals"]["saved_high"], 0)
        self.assertTrue(any("how often" in w for w in a["warnings"]))

    def test_the_first_one_is_the_highest_priority(self):
        a = core.analyze(sheet(["decided"], ["chased"], ["retyped"]))
        best = max(r["priority"] for r in a["steps"])
        self.assertEqual(a["first"]["priority"], best)


class Money(unittest.TestCase):

    def test_no_rate_means_no_dollar_figure_anywhere(self):
        a = core.analyze(sheet(["retyped"], ["chased"]))
        for row in a["steps"]:
            self.assertNotIn("money_low", row)
        self.assertTrue(any("hourly cost" in w for w in a["warnings"]))
        self.assertNotIn("$", core.to_markdown(sheet(["retyped"]), a))

    def test_a_rate_given_is_shown_with_its_arithmetic(self):
        doc = sheet(["retyped"], hourly_cost=45)
        row = core.analyze(doc)["steps"][0]
        self.assertIn("money_how", row)
        self.assertIn("$45", row["money_how"])
        self.assertIn("–", row["money_how"])


class TheOnePager(unittest.TestCase):

    def setUp(self):
        self.doc = sheet(["retyped", "chased"], ["decided"])
        self.a = core.analyze(self.doc)
        self.md = core.to_markdown(self.doc, self.a)
        self.txt = core.to_text(self.doc, self.a)

    def test_it_says_hours_are_not_money_and_not_a_person(self):
        for text in (self.md, self.txt):
            self.assertIn("not the same as a person freed up", text)

    def test_it_says_nothing_goes_to_zero(self):
        for text in (self.md, self.txt):
            self.assertIn("No step on this page goes to zero", text)

    def test_it_never_promises(self):
        for text in (self.md, self.txt):
            self.assertIn("Nothing on this page is a promise", text)
            for banned in ("guarantee", "will save you", "ROI of", "proven"):
                self.assertNotIn(banned, text)

    def test_every_headline_number_is_a_range(self):
        head = self.md.split("## Start here")[0]
        self.assertIn("–", head)


class Starters(unittest.TestCase):

    def test_the_files_all_load_with_nothing_reported_wrong(self):
        starters.reload()
        self.assertTrue(starters.list_starters())
        self.assertEqual(starters.problems(), [])

    def test_no_starter_seeds_a_volume(self):
        """A number nobody was asked for must not reach a client's sheet."""
        for meta in starters.list_starters():
            doc = starters.get_starter(meta["key"])
            for step in doc["steps"]:
                self.assertEqual(step["runs_per_month"], 0,
                                 "%s seeds a volume nobody stated" % meta["key"])

    def test_every_starter_analyses_and_holds_its_ranges(self):
        for meta in starters.list_starters():
            doc = starters.get_starter(meta["key"])
            for step in doc["steps"]:
                step["runs_per_month"] = 12
            a = core.analyze(doc)
            self.assertTrue(a["first"], meta["key"])
            for row in a["steps"]:
                if row["patterns"]:
                    self.assertGreater(row["share_high"], row["share_low"],
                                       "%s / %s" % (meta["key"], row["name"]))

    def test_a_starter_cannot_be_mutated_through_the_getter(self):
        first = starters.get_starter("scheduling")
        first["steps"][0]["handling"].append("retyped")
        first["steps"][0]["minutes"] = 999
        second = starters.get_starter("scheduling")
        self.assertNotIn("retyped", second["steps"][0]["handling"])
        self.assertNotEqual(second["steps"][0]["minutes"], 999)

    def test_every_starter_carries_a_sample_and_a_question(self):
        for meta in starters.list_starters():
            doc = starters.get_starter(meta["key"])
            self.assertTrue(doc["sample"].strip(), meta["key"])
            self.assertTrue(doc["asks"].strip(), meta["key"])


class Normalising(unittest.TestCase):

    def test_junk_in_does_not_crash_anything(self):
        for junk in (None, {}, {"steps": None}, {"steps": [None, 3, "x"]},
                     {"steps": [{"minutes": "lots", "runs_per_month": "-4"}]},
                     {"hourly_cost": float("nan")}):
            core.analyze(junk)

    def test_an_unknown_handling_tag_is_dropped_not_kept(self):
        doc = core.normalize({"steps": [{"handling": ["retyped", "teleported"]}]})
        self.assertEqual(doc["steps"][0]["handling"], ["retyped"])

    def test_step_count_is_capped(self):
        doc = core.normalize({"steps": [{"name": "x"}] * 500})
        self.assertEqual(len(doc["steps"]), core.MAX_STEPS)

    def test_duplicate_ids_do_not_shadow_each_other(self):
        doc = core.normalize({"steps": [{"id": "a", "name": "one"},
                                        {"id": "a", "name": "two"}]})
        self.assertEqual(len({s["id"] for s in doc["steps"]}), len(doc["steps"]))


class ComingFromTheMapper(unittest.TestCase):

    def handoff(self, **kw):
        base = {
            "format": "flowmap-handoff", "v": 1,
            "source": {"name": "Quote to cash", "client": "Northgate Mechanical",
                       "industry": "HVAC", "map_id": "m1"},
            "map": {"steps": [
                {"id": "s1", "kind": "start", "name": "Start"},
                {"id": "s2", "name": "Type it in", "role": "Office",
                 "system": "The software", "touch_min": 12},
                {"id": "s3", "kind": "end", "name": "Done"},
            ]},
        }
        base.update(kw)
        return base

    def test_times_and_names_come_across(self):
        doc = core.from_flowmap(self.handoff())
        self.assertEqual(doc["client"], "Northgate Mechanical")
        self.assertEqual(len(doc["steps"]), 1)          # start and end dropped
        self.assertEqual(doc["steps"][0]["minutes"], 12)
        self.assertEqual(doc["steps"][0]["who"], "Office")

    def test_what_happens_to_the_information_is_never_guessed(self):
        """A map never recorded it. Inventing it would put a tick on a client's
        sheet the client did not make."""
        doc = core.from_flowmap(self.handoff())
        for step in doc["steps"]:
            self.assertEqual(step["handling"], [])

    def test_volume_never_comes_across(self):
        doc = core.from_flowmap(self.handoff())
        self.assertEqual(doc["steps"][0]["runs_per_month"], 0)

    def test_a_newer_file_is_refused_in_plain_english(self):
        with self.assertRaises(ValueError) as cm:
            core.from_flowmap(self.handoff(v=99))
        self.assertIn("newer Workflow Mapper", str(cm.exception))

    def test_the_wrong_kind_of_file_is_refused(self):
        for bad in ({}, {"format": "something-else", "v": 1}, "not a dict"):
            with self.assertRaises(ValueError):
                core.from_flowmap(bad)


if __name__ == "__main__":
    unittest.main()
