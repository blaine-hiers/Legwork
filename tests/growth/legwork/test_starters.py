"""The starters are files, and the loader has to behave like one that reads files.

Two rules carry the weight:

  * **A file cannot seed a volume.** `runs_per_month` is the one number that has
    to come out of the owner's mouth, and a starter that seeded it would put a
    figure nobody stated on a sheet with their company name at the top.
  * **A broken file is reported, never dropped in silence.** A starter that
    vanished quietly looks exactly like one nobody ever wrote.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = next(p for p in _TESTS.parents if (p / "_shared" / "appkit.py").is_file())
_APP = _ROOT / _TESTS.relative_to(_ROOT / "tests")
sys.path.insert(0, str(_APP))
sys.path.insert(0, str(_ROOT / "_shared"))

import patterns      # noqa: E402
import starters      # noqa: E402

GOOD = {
    "key": "test-one", "order": 10, "title": "A test workflow",
    "industry": "Testing", "blurb": "A blurb.", "asks": "A question?",
    "sample": "some text",
    "steps": [{"name": "Do a thing", "who": "Someone", "system": "A system",
               "minutes": 12, "handling": ["retyped"], "note": ""}],
}


class WithATempFolder(unittest.TestCase):
    """Point the loader at a folder this test owns, then put it back."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="starters-test-"))
        self.real = starters.STARTERS_DIR
        starters.STARTERS_DIR = self.tmp
        starters.reload()

    def tearDown(self):
        starters.STARTERS_DIR = self.real
        starters.reload()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, obj):
        path = self.tmp / name
        if isinstance(obj, str):
            path.write_text(obj, encoding="utf-8")
        else:
            path.write_text(json.dumps(obj), encoding="utf-8")
        starters.reload()
        return path


class TheShippedFiles(unittest.TestCase):

    def test_they_all_load_clean(self):
        starters.reload()
        self.assertEqual(starters.problems(), [])
        self.assertGreaterEqual(len(starters.list_starters()), 5)

    def test_every_handling_word_used_is_a_real_one(self):
        """A typo in a file would silently remove a step's only saving."""
        known = {h["key"] for h in patterns.HANDLING}
        for meta in starters.list_starters():
            doc = starters.get_starter(meta["key"])
            for step in doc["steps"]:
                for word in step["handling"]:
                    self.assertIn(word, known, "%s / %s" % (meta["key"], step["name"]))

    def test_no_file_on_disk_carries_a_volume(self):
        for path in starters.STARTERS_DIR.glob("*.json"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            for step in raw["steps"]:
                self.assertNotIn("runs_per_month", step, path.name)

    def test_the_readme_is_there_and_is_not_loaded_as_a_starter(self):
        self.assertTrue((starters.STARTERS_DIR / "_README.md").is_file())
        self.assertNotIn("_README", [m["key"] for m in starters.list_starters()])


class AddingAFileAddsAStarter(WithATempFolder):

    def test_a_new_file_appears_with_no_code_change(self):
        self.write("test-one.json", GOOD)
        self.assertEqual([m["key"] for m in starters.list_starters()], ["test-one"])

    def test_order_decides_the_picker_and_missing_order_goes_last(self):
        self.write("b.json", dict(GOOD, key="b", order=20))
        self.write("a.json", dict(GOOD, key="a", order=10))
        no_order = dict(GOOD, key="z")
        no_order.pop("order")
        self.write("z.json", no_order)
        self.assertEqual([m["key"] for m in starters.list_starters()], ["a", "b", "z"])


class AFileCannotSeedAVolume(WithATempFolder):

    def test_it_is_forced_to_zero(self):
        seeded = dict(GOOD)
        seeded["steps"] = [dict(GOOD["steps"][0], runs_per_month=40)]
        self.write("test-one.json", seeded)
        doc = starters.get_starter("test-one")
        self.assertEqual(doc["steps"][0]["runs_per_month"], 0)

    def test_and_the_attempt_is_reported_on_screen(self):
        seeded = dict(GOOD)
        seeded["steps"] = [dict(GOOD["steps"][0], runs_per_month=40)]
        self.write("test-one.json", seeded)
        why = " ".join(p["why"] for p in starters.problems())
        self.assertIn("runs_per_month", why)


class ABrokenFileIsReportedNotSwallowed(WithATempFolder):

    def test_unreadable_json(self):
        self.write("bad.json", "{ this is not json")
        self.assertEqual(starters.list_starters(), [])
        self.assertEqual(len(starters.problems()), 1)
        self.assertIn("bad.json", starters.problems()[0]["file"])

    def test_a_missing_required_field_names_the_field(self):
        short = dict(GOOD)
        short.pop("asks")
        self.write("short.json", short)
        self.assertEqual(starters.list_starters(), [])
        self.assertIn("asks", starters.problems()[0]["why"])

    def test_no_usable_steps(self):
        self.write("empty.json", dict(GOOD, steps=[]))
        self.assertIn("Missing", starters.problems()[0]["why"])

    def test_two_files_claiming_one_key_keeps_the_first_and_says_so(self):
        self.write("a-one.json", dict(GOOD, key="same", order=10))
        self.write("b-two.json", dict(GOOD, key="same", order=20, title="Second"))
        self.assertEqual(len(starters.list_starters()), 1)
        self.assertEqual(starters.list_starters()[0]["title"], "A test workflow")
        self.assertIn("Two files", starters.problems()[0]["why"])

    def test_one_bad_file_does_not_take_the_good_ones_with_it(self):
        self.write("good.json", GOOD)
        self.write("bad.json", "{{{")
        self.assertEqual([m["key"] for m in starters.list_starters()], ["test-one"])
        self.assertEqual(len(starters.problems()), 1)

    def test_a_missing_folder_is_survivable_and_said_out_loud(self):
        starters.STARTERS_DIR = self.tmp / "gone"
        starters.reload()
        self.assertEqual(starters.list_starters(), [])
        self.assertTrue(starters.problems())
        self.assertIn("still runs", starters.problems()[0]["why"])


class TheCacheCannotBeEditedFromOutside(WithATempFolder):

    def test_mutating_what_you_got_back_does_not_change_the_next_one(self):
        self.write("test-one.json", GOOD)
        first = starters.get_starter("test-one")
        first["steps"][0]["handling"].append("chased")
        first["steps"][0]["minutes"] = 999
        second = starters.get_starter("test-one")
        self.assertNotIn("chased", second["steps"][0]["handling"])
        self.assertEqual(second["steps"][0]["minutes"], 12)


if __name__ == "__main__":
    unittest.main()
