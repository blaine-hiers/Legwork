"""The arithmetic, and the rule it exists to hold.

The headline test in here is `test_no_step_can_ever_report_a_single_figure`.
`05` §8 forbids a single-point figure on a client's page, and this app is the
one that puts figures in front of a prospect before anybody has been paid. Every
other test here is support for that one.
"""

import re
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


# Every shape a rendered range comes in across `to_markdown`/`to_text`: an
# en-dash pair ("1.2–1.8 hrs", "$0–$45"), a percent pair written with "to"
# ("0% to 18% of it"), and a percent pair in parens with a plain hyphen
# ("(0%-18%)"). issue #1 was a range that survived every upstream guard and
# still printed with both ends equal, so the check that matters reads the
# rendered text itself rather than the numbers that produced it.
_RANGE_PATTERNS = [
    re.compile(r"\$?(\d+(?:\.\d+)?)\s*–\s*\$?(\d+(?:\.\d+)?)"),
    re.compile(r"(\d+(?:\.\d+)?)%\s+to\s+(\d+(?:\.\d+)?)%"),
    re.compile(r"\((\d+(?:\.\d+)?)%-(\d+(?:\.\d+)?)%\)"),
]


def rendered_ranges(text):
    """Every low/high pair a client would actually read off this text."""
    out = []
    for pattern in _RANGE_PATTERNS:
        for lo, hi in pattern.findall(text):
            out.append((float(lo), float(hi)))
    return out



def tenths(hours):
    """Hours as whole tenths -- the grid every hours figure is shown on."""
    return int(round(hours * 10))


def assert_roles_reconcile(test, a, case):
    """The by-role invariant: each role shows a clean one-decimal, non-negative
    figure, the roles' tenths add up to the total's tenths exactly, and so the
    displayed role hours sum to the displayed total at that one decimal."""
    hours = [r["hours_month"] for r in a["by_role"]]
    for h in hours:
        test.assertGreaterEqual(h, 0, case)
        test.assertEqual(h, round(h, 1), "%s: %r" % (case, h))
    test.assertEqual(sum(tenths(h) for h in hours), tenths(a["totals"]["hours_month"]), case)
    test.assertEqual(round(sum(hours), 1), a["totals"]["hours_month"], case)

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

    def test_the_display_guard_fires_when_rounding_still_collapses_it(self):
        """issue #1's second guard: the fractions can be fine and the figure
        actually printed can still be a single point, one rounding later.
        A pair that isn't a range at all is the model-broke case this
        guards; see `TheRangeCollapseFix` for what a real small quantity
        (e.g. half a minute) renders as instead."""
        with self.assertRaises(patterns.SavingsError):
            core._finest_range(0.5, 0.5)     # collapses at every unit tried

    def test_a_real_range_finer_than_a_tenth_of_a_second_still_renders(self):
        """The form takes 0.01 minutes run 0.5 times a month. That is a
        real, distinct range too fine for any unit here, and it must
        render, not raise into a 500."""
        self.assertEqual(core._finest_range(0.0, 0.00001), "0–0.1 sec")
        for minutes, runs in ((0.01, 0.01), (0.01, 0.5), (0.05, 0.05),
                              (0.1, 0.05), (0.25, 0.01), (0.5, 0.01)):
            for handling in (["chased"], ["chased", "decided"]):
                core.analyze({"hourly_cost": 120, "steps": [{"minutes": minutes,
                              "runs_per_month": runs, "handling": handling}]})

    def test_the_hours_in_money_how_never_collapse_to_one_figure(self):
        """The parenthetical hours used to round each end independently
        to four places: 0.01 min run 0.62 times read "0.0001–0.0001 hrs"."""
        a = core.analyze({"hourly_cost": 120, "steps": [{"minutes": 0.01,
                         "runs_per_month": 0.62, "handling": ["chased"]}]})
        how = a["steps"][0]["money_how"]
        self.assertIn("(0–0.0001 hrs)", how)


class TheRangeCollapseFix(unittest.TestCase):
    """issue #1: a saving that survives every upstream guard as a real range
    can still round to "0-0" (or "0% to 0%") by the time it reaches the
    page. Every case below renders the actual `to_markdown`/`to_text` output
    and checks what a client would actually read, not the numbers behind it.
    """

    def test_a_starter_as_loaded_never_renders_a_collapsed_range(self):
        """Every starter forces zero volume on load (`04`'s own rule) while
        shipping every step pre-ticked -- exactly the state the bug lived in."""
        for meta in starters.list_starters():
            doc = starters.get_starter(meta["key"])
            a = core.analyze(doc)
            self.assertTrue(a["totals"]["pending"], meta["key"])
            for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
                self.assertNotIn("0–0", text, meta["key"])
                for low, high in rendered_ranges(text):
                    self.assertNotEqual(low, high,
                                        "%s: %r" % (meta["key"], text))

    def test_a_small_but_real_quantity_still_renders_a_range(self):
        """The exact repro from issue #1: 2 minutes, run once a month."""
        doc = core.blank_demo("probe")
        doc["steps"] = [{"name": "Tiny rare step", "minutes": 2,
                         "runs_per_month": 1, "handling": ["decided"]}]
        a = core.analyze(doc)
        row = a["steps"][0]
        self.assertFalse(row["quantity_pending"])
        self.assertEqual((row["saved_low"], row["saved_high"]), (0, 0))
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            ranges = rendered_ranges(text)
            self.assertTrue(ranges, text)
            for low, high in ranges:
                self.assertNotEqual(low, high, text)

    def test_a_normal_step_renders_a_plain_range_untouched(self):
        """Nothing here should need the minute-level fallback at all."""
        doc = sheet(["retyped", "chased"])
        a = core.analyze(doc)
        self.assertFalse(a["steps"][0]["quantity_pending"])
        self.assertIn("hrs", a["steps"][0]["addressable"])
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            ranges = rendered_ranges(text)
            self.assertTrue(ranges, text)
            for low, high in ranges:
                self.assertNotEqual(low, high, text)

    def test_real_volume_with_nothing_ticked_is_not_the_same_as_pending(self):
        """Review finding #1: real hours on the sheet but no pattern ticked
        anywhere fell into the same `else` as "ticked, no volume yet" and
        rendered the exact "0-0 hrs / 0% to 0%" this issue exists to kill."""
        doc = sheet([], minutes=30, runs=10)          # real time, nothing ticked
        a = core.analyze(doc)
        t = a["totals"]
        self.assertGreater(t["hours_month"], 0)
        self.assertTrue(t["nothing_ticked"])
        self.assertFalse(t["pending"])
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            self.assertNotIn("0–0", text)
            self.assertNotIn("0% to 0%", text)
            for low, high in rendered_ranges(text):
                self.assertNotEqual(low, high, text)

    def test_a_small_real_quantity_renders_instead_of_crashing(self):
        """Review finding #2 (the worst of the three): half a minute, run
        every other month, with `chased` -- a value an owner can legitimately
        type into this app's own form -- raised SavingsError out through
        analyze()/to_markdown()/to_text() instead of rendering. The guard
        must stay reachable for a genuinely broken model (see the display
        guard test above), but not for input this ordinary."""
        doc = {"name": "T", "client": "C", "hourly_cost": 0,
               "steps": [{"id": "s1", "name": "Tiny real step", "minutes": 0.5,
                          "runs_per_month": 0.5, "handling": ["chased"]}]}
        a = core.analyze(doc)                          # must not raise
        row = a["steps"][0]
        self.assertFalse(row["quantity_pending"])
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            ranges = rendered_ranges(text)
            self.assertTrue(ranges, text)
            for low, high in ranges:
                self.assertNotEqual(low, high, text)

    def test_totals_do_not_double_round_into_a_collapse(self):
        """Review finding #3: totals["saved_low"]/["saved_high"] were summed
        from each step's already-rounded hours and rounded again, which
        could collapse the total even while totals["addressable"] (built
        from the same raw claim, rounded once) showed a real range."""
        doc = {"name": "T", "hourly_cost": 0, "steps": [
            {"id": "s1", "name": "A", "minutes": 2, "runs_per_month": 2,
             "handling": ["decided"]},
            {"id": "s2", "name": "B", "minutes": 1.4, "runs_per_month": 2,
             "handling": ["chased"]},
        ]}
        a = core.analyze(doc)
        t = a["totals"]
        self.assertFalse(t["nothing_ticked"])
        self.assertFalse(t["pending"])
        self.assertNotEqual(t["saved_low"], t["saved_high"])
        self.assertIn("–", t["addressable"])
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            for low, high in rendered_ranges(text):
                self.assertNotEqual(low, high, text)


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

    def test_a_small_real_quantity_does_not_collapse_the_money_figure(self):
        """The PR review's own repro: 2 minutes, run once a month, $50/hr.
        The step's hours already stay a real range via `_finest_range` --
        this is the money figure computed from the same coarse
        `saved_low`/`saved_high` `_hours()` rounds to, which was never
        wired up to the escalated-precision fix."""
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        a = core.analyze(doc)
        row = a["steps"][0]
        self.assertEqual((row["saved_low"], row["saved_high"]), (0, 0))
        self.assertNotEqual(row["money_low"], row["money_high"])
        for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
            self.assertNotIn("$0–$0 ", text)
            for low, high in rendered_ranges(text):
                self.assertNotEqual(low, high, text)

    def test_a_sweep_of_small_quantities_never_collapses_the_money_figure(self):
        """The reviewer's own sweep: minutes in {0.5,1,2,3,5} × runs_per_month
        in {0.5,1,2} at $40/hr collapsed money in 14/15 combinations before
        this fix."""
        for minutes in (0.5, 1, 2, 3, 5):
            for runs in (0.5, 1, 2):
                doc = {"name": "T", "hourly_cost": 40, "steps": [
                    {"id": "s1", "name": "s", "minutes": minutes,
                     "runs_per_month": runs, "handling": ["decided"]},
                ]}
                a = core.analyze(doc)
                row = a["steps"][0]
                case = "minutes=%s runs=%s" % (minutes, runs)
                self.assertNotEqual(row["money_low"], row["money_high"], case)
                for text in (core.to_markdown(doc, a), core.to_text(doc, a)):
                    for low, high in rendered_ranges(text):
                        self.assertNotEqual(low, high, "%s: %s" % (case, text))

    def test_money_how_states_the_same_hours_as_the_addressable_line(self):
        """The money sentence must not quote a different hours figure than
        the one shown a couple of lines above it for the same step."""
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertIn(row["addressable"], row["money_how"])


# Every dollar figure `money_how` can state, matched as a whole token so
# "under $0.01" isn't split on its own space. Used below to pull the
# equation's stated hours and its stated money apart and check one against
# the other, and to check every currency figure's own decimal count.
_MONEY_TOKEN = r"(?:under \$0\.01|\$0|\$\d+(?:\.\d+)?)"
_MONEY_EQUATION = re.compile(
    r"\(?([\d.]+)–([\d.]+) hrs\)? × \$(\d+) an hour [=≈] "
    r"(%s)–(%s) a month" % (_MONEY_TOKEN, _MONEY_TOKEN)
)


def _money_amount(token):
    """A `money_how` currency token as a float, or `None` for the "under a
    cent" text, which has no single number to check arithmetic against."""
    return None if token.startswith("under") else float(token.lstrip("$") or 0)


class MoneyHowEquation(unittest.TestCase):
    """Review finding 1: `money_how` stated `addressable` (which can be in
    minutes or seconds) multiplied by an hourly rate, which is dimensionally
    wrong -- an hourly rate only multiplies hours. Every case here checks
    the sentence a business owner would actually try to verify: the hours
    figure it states, times the rate it states, comes out to the money it
    states, within the rounding the sentence itself is doing."""

    def _check_equation(self, how, case=""):
        m = _MONEY_EQUATION.search(how)
        self.assertIsNotNone(m, "%s: no equation found in %r" % (case, how))
        hrs_low, hrs_high, rate, money_low_s, money_high_s = m.groups()
        rate = float(rate)
        for hrs, money_s in ((hrs_low, money_low_s), (hrs_high, money_high_s)):
            amount = _money_amount(money_s)
            if amount is None:
                continue    # "under $0.01" -- nothing numeric to check
            calc = float(hrs) * rate
            self.assertLess(
                abs(calc - amount), max(0.02, 0.5 * amount),
                "%s: %s hrs × $%s ≈ $%.4f calculated, but %r shown in %r"
                % (case, hrs, rate, calc, money_s, how),
            )

    def test_equation_checks_out_when_addressable_is_minutes(self):
        """The review's own repro: was '0–0.4 min × $50 an hour = $0–$0.3 a
        month' -- 0.4 × 50 = 20, nowhere near $0.30."""
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertTrue(row["addressable"].endswith("min"), row["addressable"])
        self._check_equation(row["money_how"])

    def test_equation_checks_out_when_addressable_is_seconds(self):
        """The review's second repro: was '9–12 sec × $40 an hour = $0.11–
        $0.14 a month' -- 12 × 40 = 480, nowhere near $0.14."""
        doc = {"name": "T", "hourly_cost": 40, "steps": [
            {"id": "s1", "name": "s", "minutes": 0.5,
             "runs_per_month": 0.5, "handling": ["chased"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertTrue(row["addressable"].endswith("sec"), row["addressable"])
        self._check_equation(row["money_how"])

    def test_equation_still_checks_out_when_addressable_is_already_hours(self):
        """When a step's claim is large enough that `addressable` stays in
        hours, the equation was always correct -- this fix must not touch
        that case (`04`)."""
        doc = sheet(["retyped"], hourly_cost=45)   # 30 min x 10 runs/month
        row = core.analyze(doc)["steps"][0]
        self.assertTrue(row["addressable"].endswith("hrs"), row["addressable"])
        self._check_equation(row["money_how"])

    def test_time_phrase_in_the_equation_matches_the_addressable_line_above_it(self):
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertIn(row["addressable"], row["money_how"])


class MoneyCurrencyFormat(unittest.TestCase):
    """Review finding 2: `_finest_money`'s escalation ladder could print a
    fraction of a cent ("$0.026–$0.034") or a one-decimal dollar figure
    ("$0.3") -- neither of which is a currency figure a business owner can
    act on. Every dollar figure shown must have 0 or exactly 2 decimals,
    or say "under $0.01" when there's truly less than a cent to show."""

    def _every_currency_token_is_well_formed(self, text, case=""):
        for m in re.finditer(r"\$(\d+(?:\.\d+)?)", text):
            if "." in m.group(1):
                places = m.group(1).split(".")[1]
                self.assertEqual(
                    len(places), 2,
                    "%s: %r has %d decimal places in %r"
                    % (case, m.group(0), len(places), text),
                )

    def test_a_two_to_four_cent_range_still_renders_as_real_cents(self):
        """The review's own repro (minutes=0.5, runs=0.5, $10/hr, "chased")
        gave money_low=0.026, money_high=0.034 -- 2.6 to 3.4 cents, i.e.
        *above* a cent, just formatted with too many decimal places
        ('$0.026-$0.034'). That range must still read as real cents, not
        collapse to the same figure and not fall back to "under a cent"
        (which is reserved for amounts that truly haven't reached one)."""
        doc = {"name": "T", "hourly_cost": 10, "steps": [
            {"id": "s1", "name": "s", "minutes": 0.5,
             "runs_per_month": 0.5, "handling": ["chased"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertNotIn("under $0.01", row["money_how"])
        self.assertNotEqual(row["money_low"], row["money_high"])
        self._every_currency_token_is_well_formed(row["money_how"])

    def test_an_amount_under_a_cent_says_so_instead_of_a_fraction_of_one(self):
        """A step small enough that even the high end is worth less than a
        cent (minutes=0.5, runs=0.5, $1/hr, "decided") renders "under
        $0.01" instead of a sub-cent figure nobody could act on."""
        doc = {"name": "T", "hourly_cost": 1, "steps": [
            {"id": "s1", "name": "s", "minutes": 0.5,
             "runs_per_month": 0.5, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertLess(row["money_high"], 0.01)
        self.assertIn("under $0.01", row["money_how"])
        self._every_currency_token_is_well_formed(row["money_how"])

    def test_thirty_cents_renders_with_two_decimals_not_one(self):
        """The review's own repro: was '$0.3' instead of '$0.30'."""
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertIn("$0.30", row["money_how"])
        self.assertNotIn("$0.3 ", row["money_how"])
        self._every_currency_token_is_well_formed(row["money_how"])

    def test_zero_stays_a_bare_dollar_zero(self):
        doc = {"name": "T", "hourly_cost": 50, "steps": [
            {"id": "s1", "name": "Tiny rare step", "minutes": 2,
             "runs_per_month": 1, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertEqual(row["money_low"], 0.0)
        self.assertIn("$0–", row["money_how"])

    def test_money_low_and_high_stay_plain_numbers_for_api_consumers(self):
        """`money_low`/`money_high` are read directly by `/api/analyze` and
        the export routes, not just quoted in `money_how` -- they must stay
        numeric even in the "under a cent" case, never the display string."""
        doc = {"name": "T", "hourly_cost": 1, "steps": [
            {"id": "s1", "name": "s", "minutes": 0.5,
             "runs_per_month": 0.5, "handling": ["decided"]},
        ]}
        row = core.analyze(doc)["steps"][0]
        self.assertLess(row["money_high"], 0.01)     # the "under $0.01" case
        self.assertIsInstance(row["money_low"], float)
        self.assertIsInstance(row["money_high"], float)
        self.assertLess(row["money_low"], row["money_high"])

    def test_a_sweep_of_minutes_runs_and_rates_never_breaks_the_money_figure(self):
        """The sweep both review findings were checked against: minutes x
        runs_per_month x hourly_cost. No malformed currency and no numeric
        collapse anywhere in the grid; the stated equation checks out
        whenever `addressable` is in minutes or seconds -- the dimensional
        fix this review asked for. The hours tier is excluded from the
        equation check on purpose: it multiplies a figure `_hours()` has
        already rounded to a tenth of an hour against the raw, unrounded
        money claim, the same as it did before this fix (out of scope --
        "when addressable is already in hours, keep today's output
        unchanged") and that tenth-of-an-hour rounding can outweigh a small
        claim's own money figure, which is a pre-existing display-precision
        quirk, not the collapse or the dimensional error this review is
        about."""
        checker = MoneyHowEquation()
        for minutes in (0.5, 1, 2, 3, 5, 30, 60):
            for runs in (0.5, 1, 2, 20, 200):
                for rate in (10, 40, 50, 120):
                    doc = {"name": "T", "hourly_cost": rate, "steps": [
                        {"id": "s1", "name": "s", "minutes": minutes,
                         "runs_per_month": runs, "handling": ["decided"]},
                    ]}
                    row = core.analyze(doc)["steps"][0]
                    case = "minutes=%s runs=%s rate=%s" % (minutes, runs, rate)
                    self.assertLess(row["money_low"], row["money_high"], case)
                    how = row["money_how"]
                    self._every_currency_token_is_well_formed(how, case)
                    if not row["addressable"].endswith("hrs"):
                        checker._check_equation(how, case)
                    for text in (core.to_markdown(doc), core.to_text(doc)):
                        for low, high in rendered_ranges(text):
                            self.assertNotEqual(low, high, "%s: %s" % (case, text))


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


class ByRole(unittest.TestCase):
    """`analyze()["by_role"]` groups the same per-step rows `totals` sums
    from, by `who` -- a step with no `who` lands in an explicit "not said"
    bucket rather than disappearing into it. Because a role's hours are
    exactly the rows that belong to it, summing every role's hours must
    reproduce `totals.hours_month`, by construction, for any sheet."""

    def _doc(self, steps, hourly_cost=0, role_rates=None):
        return {
            "name": "T", "hourly_cost": hourly_cost,
            "role_rates": role_rates or {},
            "steps": [
                {"id": "s%d" % i, "name": "Step %d" % i, "who": who,
                 "minutes": minutes, "runs_per_month": runs, "handling": handling}
                for i, (who, minutes, runs, handling) in enumerate(steps)
            ],
        }

    def test_no_rates_at_all_still_rolls_up_hours_and_share(self):
        doc = self._doc([
            ("Front office", 30, 10, ["retyped"]),
            ("Technician", 60, 10, ["chased"]),
        ])
        a = core.analyze(doc)
        by_who = {r["who"]: r for r in a["by_role"]}
        self.assertEqual(set(by_who), {"Front office", "Technician"})
        self.assertEqual(by_who["Front office"]["hours_month"], 5.0)
        self.assertEqual(by_who["Technician"]["hours_month"], 10.0)
        self.assertEqual(by_who["Front office"]["share"], 33)
        self.assertEqual(by_who["Technician"]["share"], 67)

    def test_a_rated_role_and_an_unrated_role_are_labelled_differently(self):
        """The role with a stated rate names it as its own; the role
        without one still prices at `hourly_cost`, but its line says so
        plainly -- never presented as a rate for that role."""
        doc = self._doc([
            ("Front office", 30, 10, ["retyped"]),
            ("Technician", 60, 10, ["chased"]),
        ], hourly_cost=22, role_rates={"Technician": 95})
        a = core.analyze(doc)
        by_who = {r["who"]: r for r in a["by_role"]}
        self.assertTrue(by_who["Technician"]["has_own_rate"])
        self.assertIn("$95", by_who["Technician"]["money_how"])
        self.assertNotIn("blended", by_who["Technician"]["money_how"])
        self.assertFalse(by_who["Front office"]["has_own_rate"])
        self.assertIn("$22", by_who["Front office"]["money_how"])
        self.assertIn("blended", by_who["Front office"]["money_how"])

    def test_every_role_rated_names_its_own_rate(self):
        doc = self._doc([
            ("Front office", 30, 10, ["retyped"]),
            ("Technician", 60, 10, ["chased"]),
        ], role_rates={"Front office": 22, "Technician": 95})
        a = core.analyze(doc)
        for r in a["by_role"]:
            self.assertTrue(r["has_own_rate"], r["who"])
            self.assertNotIn("blended", r["money_how"])

    def test_a_step_with_no_who_lands_in_an_explicit_not_said_bucket(self):
        doc = self._doc([
            ("Front office", 30, 10, ["retyped"]),
            ("", 20, 10, ["chased"]),
        ])
        a = core.analyze(doc)
        by_who = {r["who"]: r for r in a["by_role"]}
        self.assertIn("not said", by_who)
        self.assertGreater(by_who["not said"]["hours_month"], 0)

    def test_a_literal_role_named_not_said_cannot_collide_with_the_bucket(self):
        """The exact repro: a step with a blank `who` (the bucket) and a
        step whose `who` is the literal string "not said" (a real role
        that happens to share the bucket's own label). The two must never
        render identically -- a dict keyed by `who`, the way every
        consumer of `by_role` reads it (including the tests above), must
        end up with both rows, not one silently overwriting the other."""
        doc = self._doc([
            ("   ", 30, 10, ["retyped"]),
            ("not said", 20, 10, ["chased"]),
        ])
        a = core.analyze(doc)
        self.assertEqual(len(a["by_role"]), 2)
        by_who = {r["who"]: r for r in a["by_role"]}
        self.assertEqual(len(by_who), 2,
                         "two distinct by_role rows collapsed to one key: %r"
                         % [r["who"] for r in a["by_role"]])

        bucket = next(r for r in a["by_role"] if r["not_said"])
        named = next(r for r in a["by_role"] if not r["not_said"])
        self.assertNotEqual(bucket["who"], named["who"])
        self.assertAlmostEqual(bucket["hours_month"], 5.0, places=1)     # 30 min x 10/mo
        self.assertAlmostEqual(named["hours_month"], 3.3, places=1)      # 20 min x 10/mo
        assert_roles_reconcile(self, a, "not said repro")

    def test_a_zero_effective_rate_gives_an_hours_only_line(self):
        doc = self._doc([("Front office", 30, 10, ["retyped"])])   # no rate anywhere
        a = core.analyze(doc)
        row = a["by_role"][0]
        self.assertIsNone(row["money_how"])
        self.assertIn("stays in hours", row["rate_how"])

    def test_role_rates_never_invent_a_value_for_an_unstated_role(self):
        doc = self._doc([("Ghost", 30, 10, ["retyped"])],
                         role_rates={"Someone else": 999})
        a = core.analyze(doc)
        row = a["by_role"][0]
        self.assertFalse(row["has_own_rate"])
        self.assertIsNone(row["money_how"])

    def test_per_role_hours_sum_to_the_sheet_total_across_a_sweep(self):
        """The reconciliation invariant, swept across tiny inputs where the
        old approach (each role's already-rounded hours summed, then that
        sum rounded again) could drift from `totals.hours_month`, which
        rounds the grand sum once. `_apportion_tenths` fixes the total
        first and hands out its tenths, so this now holds with `==`, not
        `assertAlmostEqual` -- also proving no per-role line ever collapses
        a range, raises, or shows malformed currency."""
        currency = MoneyCurrencyFormat()
        for minutes in (0.01, 0.05, 0.5, 1, 2, 3, 5):
            for runs in (0.01, 0.1, 1, 5, 20):
                for rate in (0, 22, 95):
                    doc = self._doc([
                        ("Front office", minutes, runs, ["retyped"]),
                        ("Technician", minutes, runs, ["chased"]),
                        ("", minutes, runs, []),
                    ], hourly_cost=rate)
                    case = "minutes=%s runs=%s rate=%s" % (minutes, runs, rate)
                    a = core.analyze(doc)
                    assert_roles_reconcile(self, a, case)
                    for r in a["by_role"]:
                        how = r.get("money_how")
                        if not how:
                            continue
                        currency._every_currency_token_is_well_formed(how, case)
                        for lo, hi in rendered_ranges(how):
                            self.assertNotEqual(lo, hi, "%s: %s" % (case, how))

    def test_roles_doing_unequal_work_reconcile_and_render_cleanly(self):
        """Roles with unequal minutes and runs -- the realistic case, and the
        one where giving the smallest role `total - others` rendered it as
        0.29999999999999893 or even a negative. Includes the reviewer's two
        counter-examples plus a seeded random sweep."""
        import random
        docs = [
            self._doc([("Front office", 12, 40, ["retyped"]), ("Technician", 22, 8, ["chased"]),
                       ("Dispatcher", 4, 5, ["chased"])], hourly_cost=25),
            self._doc([("Front office", 7.696260118067817, 9.834407365068424, ["retyped"]),
                       ("Technician", 2.9283609919160654, 8.24741163858587, ["chased"]),
                       ("", 1.8041962473375583, 1.6781639515135212, [])], hourly_cost=22),
        ]
        rng = random.Random(11)
        for _ in range(400):
            n = rng.randint(1, 8)
            docs.append(self._doc([
                (rng.choice(["Front office", "Technician", "Dispatcher", "", "not said"]),
                 10 ** rng.uniform(-2, 4), 10 ** rng.uniform(-2, 3),
                 rng.choice([["retyped"], ["chased"], []]))
                for _ in range(n)], hourly_cost=rng.choice([0, 22, 95])))
        for i, doc in enumerate(docs):
            a = core.analyze(doc)
            assert_roles_reconcile(self, a, "doc %d" % i)
            text = core.to_text(doc) if hasattr(core, "to_text") else ""
            self.assertNotRegex(text, r"\d\.\d{5,}", "doc %d renders float noise" % i)

    def test_per_role_hours_sum_exactly_at_extreme_magnitudes_and_max_steps(self):
        """The reviewer's own repro: a 34-step sheet at roughly a million
        minutes/runs found a 3.8e-6 drift under the old approach. Swept
        here up to `_num`'s own field ceiling (1e9) and at `MAX_STEPS`
        steps, where the old per-role-then-re-round approach had the most
        room to disagree with `totals.hours_month`."""
        roles = ["Front office", "Technician", "Dispatcher", ""]
        for minutes, runs in ((1_000, 1_000), (1_000_000, 1_000_000),
                              (1e9, 1e9)):
            steps = [
                (roles[i % len(roles)], minutes + i, runs + i, ["chased"])
                for i in range(core.MAX_STEPS)
            ]
            doc = self._doc(steps, hourly_cost=37)
            case = "minutes=%s runs=%s" % (minutes, runs)
            a = core.analyze(doc)
            self.assertEqual(len(a["steps"]), core.MAX_STEPS, case)
            assert_roles_reconcile(self, a, case)


if __name__ == "__main__":
    unittest.main()
