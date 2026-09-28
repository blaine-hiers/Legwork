"""Real-browser tests, driven with Playwright when it is available.

Everything else in this suite checks app.js the way `TheSaveLoop` and its
neighbours in test_api.py do: no JS engine here, so the source is checked
structurally and its algorithms are replayed in Python against the real
HTTP endpoints. That is enough to prove a rule is coded the right shape,
but it cannot actually race two requests against each other, and it cannot
tell a swallowed real bug from a swallowed already-handled one — both of
those need a real page.

**This file will not run anywhere Playwright and a Chromium build are not
installed** (`pip install playwright && playwright install chromium`).
Every class below skips cleanly, with a reason, when either is missing —
so a CI job that has not installed Playwright sees these as skipped, not
failed, and this is not a dependency the app itself picks up (it's a
`py -m pip`-installed *test* tool, same category as `unittest` itself).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = next(p for p in _TESTS.parents if (p / "_shared" / "appkit.py").is_file())
_APP = _ROOT / _TESTS.relative_to(_ROOT / "tests")
sys.path.insert(0, str(_APP))
sys.path.insert(0, str(_ROOT / "_shared"))

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_IMPORTABLE = True
except ImportError:
    _PLAYWRIGHT_IMPORTABLE = False

_TMP = tempfile.mkdtemp(prefix="demogen-browser-test-")

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
_PLAYWRIGHT = None
_BROWSER = None
_SKIP_REASON = None


def setUpModule():
    global BASE, SERVER, _PLAYWRIGHT, _BROWSER, _SKIP_REASON
    SERVER, BASE = appmod.app.serve_background()
    if not _PLAYWRIGHT_IMPORTABLE:
        _SKIP_REASON = "playwright is not installed (pip install playwright)"
        return
    try:
        _PLAYWRIGHT = sync_playwright().start()
        _BROWSER = _PLAYWRIGHT.chromium.launch()
    except Exception as e:      # noqa: BLE001 - any launch failure just means "skip"
        _SKIP_REASON = "chromium is not available for playwright: %s" % e
        _PLAYWRIGHT = None
        _BROWSER = None


def tearDownModule():
    global SERVER, _PLAYWRIGHT, _BROWSER
    # Each of these owns its own process (Chromium) or thread (the HTTP
    # server); closing/stopping through the library's own API is what tears
    # that process down cleanly, rather than hunting a PID by hand.
    if _BROWSER:
        _BROWSER.close()
    if _PLAYWRIGHT:
        _PLAYWRIGHT.stop()
    if SERVER:
        SERVER.shutdown()
        SERVER.server_close()
    shutil.rmtree(_TMP, ignore_errors=True)


def call(method, path, body=None):
    """The same tiny HTTP helper test_api.py uses, for setup/verification
    that does not need a browser at all."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read().decode())


class _BrowserCase(unittest.TestCase):
    """Common setup: skip with a reason if Playwright/Chromium is missing,
    otherwise a fresh page with pageerror capture, booted against the real
    app."""

    def setUp(self):
        if _SKIP_REASON:
            self.skipTest(_SKIP_REASON)
        self.page = _BROWSER.new_page()
        self.pageerrors = []
        self.page.on("pageerror", lambda exc: self.pageerrors.append(str(exc)))
        self.page.goto(BASE + "/")
        self.page.wait_for_selector('html[data-boot="ok"]', timeout=10000)

    def tearDown(self):
        if not _SKIP_REASON:
            self.page.close()

    def start_from_nothing(self):
        """Drives the real 'Start a sheet' -> 'Start from nothing' flow and
        returns the new sheet's id, read the same way the page itself tracks
        it (localStorage)."""
        self.page.click("#btnNew")
        self.page.click("text=Start from nothing")
        self.page.wait_for_selector("#sheetBody:not(.hidden)", timeout=10000)
        return self.page.evaluate("() => localStorage.getItem('demogen.last')")

    def open_sheet(self, sheet_id):
        """Only correct while at most one sheet exists in the sidebar — see
        create_and_open/open_by_client for anything with two sheets in play.
        Row order comes from the last time the page itself fetched the
        list (boot or reload); a separate fetch made later can disagree
        with it the moment something updates a sheet's timestamp, so this
        is not used once a second sheet is on screen."""
        self.page.locator("#sheetList .list-item").nth(0).click()
        self.page.wait_for_function(
            "id => localStorage.getItem('demogen.last') === id",
            arg=sheet_id, timeout=10000)

    def create_and_open(self, starter, client):
        """Creates a sheet with a distinct, human-visible name and opens it
        by clicking that name — robust to the sidebar re-sorting sheets by
        recency, which by-index lookup is not."""
        _, r = call("POST", "/api/sheets", {"starter": starter, "client": client})
        self.page.reload()
        self.page.wait_for_selector('html[data-boot="ok"]', timeout=10000)
        self.open_by_client(client)
        return r["sheet"]["id"]

    def open_by_client(self, client):
        self.page.click('#sheetList .list-item:has-text("%s")' % client)
        self.page.wait_for_function(
            "text => document.querySelector('#fClient').value === text",
            arg=client, timeout=10000)


@unittest.skipUnless(_PLAYWRIGHT_IMPORTABLE, "playwright is not installed")
class SheetSwitchDoesNotLoseAnEdit(_BrowserCase):
    """#13: an edit made just before switching sheets must survive the
    switch. Drives the exact race the issue describes: edit A, switch to B
    about 120ms later — well inside the 550ms save debounce — then check
    what actually got written for A."""

    def test_an_edit_just_before_switching_sheets_is_saved(self):
        id_a = self.create_and_open("scheduling", "Sheet A original")
        self.create_and_open("field-paperwork", "Sheet B original")

        self.open_by_client("Sheet A original")
        self.page.fill("#fClient", "Edited right before the switch")
        self.page.wait_for_timeout(120)     # well inside the 550ms debounce
        self.open_by_client("Sheet B original")

        # Give the flush every chance to have actually landed before asking.
        self.page.wait_for_timeout(300)
        _, back = call("GET", "/api/sheets/" + id_a)
        self.assertEqual(back["sheet"]["client"], "Edited right before the switch")


if __name__ == "__main__":
    unittest.main()
