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
import time
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

    def delay_analyze_for(self, sheet_id, seconds):
        """Makes the server sleep before answering /api/analyze for exactly
        this sheet id, leaving every other request untouched. Delaying on
        the server side (each request its own thread in the
        ThreadingHTTPServer under test) rather than via Playwright's route
        interception matters here: a route handler that blocks with
        time.sleep() blocks Playwright's own driver loop right along with
        it, which serialises away the very race this test needs to create.
        Restored by the returned callable — call it in tearDown/finally.
        """
        routes = appmod.app._routes
        for i, (method, rx, fn) in enumerate(routes):
            if method == "POST" and fn.__name__ == "analyze_body":
                original = fn

                def delayed(req, _original=original):
                    if (req.json() or {}).get("id") == sheet_id:
                        time.sleep(seconds)
                    return _original(req)

                routes[i] = (method, rx, delayed)
                return lambda: routes.__setitem__(i, (method, rx, original))
        raise AssertionError("no POST /api/analyze route found to delay")


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


@unittest.skipUnless(_PLAYWRIGHT_IMPORTABLE, "playwright is not installed")
class StaleAnalyzeReplyDoesNotRepaint(_BrowserCase):
    """#14: a late `/api/analyze` reply from a sheet that is no longer open
    must not repaint the totals panel of the sheet that is. Delays sheet
    A's analyze reply and switches to B before it lands."""

    def test_switching_before_a_delayed_reply_lands_keeps_bs_totals(self):
        id_a = self.create_and_open("scheduling", "Sheet A original")        # 4 steps
        self.create_and_open("field-paperwork", "Sheet B original")          # 5 steps
        self.open_by_client("Sheet A original")

        restore = self.delay_analyze_for(id_a, 1.2)
        try:
            self.page.fill("#fRate", "50")    # oninput -> touched() -> recompute()
            self.page.wait_for_timeout(350)   # past the 220ms recompute debounce:
                                               # A's (now delayed) request is in flight
            self.open_by_client("Sheet B original")
            self.assertIn("5 steps", self.page.locator("#totals").inner_text())

            self.page.wait_for_timeout(1500)  # past the 1.2s delay: A's reply lands
            totals_text = self.page.locator("#totals").inner_text()
            self.assertIn("5 steps", totals_text,
                         "a stale reply from sheet A repainted B's totals panel")
            self.assertNotIn("4 steps", totals_text)
        finally:
            restore()


@unittest.skipUnless(_PLAYWRIGHT_IMPORTABLE, "playwright is not installed")
class GuardedErrorsStaySilentRealBugsSurface(_BrowserCase):
    """#6, both halves. A failure `UI.guard()` already toasted must produce
    no pageerror (that was the original bug: it produced one anyway). A
    genuine bug thrown inside one of those same `.then()` chains — nothing
    to do with what guard() caught — must still surface as one, the way it
    would with no terminal .catch() at all."""

    def test_a_guard_toasted_failure_produces_no_pageerror(self):
        def fail_create(route, request):
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"error": "boom"}))

        self.page.route("**/api/sheets", lambda route, request:
                        fail_create(route, request) if request.method == "POST"
                        else route.continue_())

        self.page.click("#btnNew")
        self.page.click("text=Start from nothing")
        self.page.wait_for_selector("#toasts .toast.bad", timeout=10000)
        self.assertIn("boom", self.page.locator("#toasts .toast.bad").inner_text())

        self.page.wait_for_timeout(300)
        self.assertEqual(self.pageerrors, [],
                         "an already-toasted guard() failure must not also "
                         "surface as a pageerror")

    def test_an_unrelated_bug_in_the_same_chain_still_surfaces(self):
        """Reproduces the reviewer's finding directly: make the code that
        runs after a successful, guarded fetch throw a real TypeError, by
        having the server hand `open()` a reply with no `sheet` in it."""
        id_a = self.start_from_nothing()

        def corrupt_reply(route, request):
            if request.method == "GET":
                route.fulfill(status=200, content_type="application/json",
                              body="{}")
            else:
                route.continue_()

        self.page.route("**/api/sheets/%s" % id_a, corrupt_reply)
        self.open_sheet(id_a)         # re-opens the same sheet -> hits the route

        self.page.wait_for_timeout(500)
        self.assertTrue(self.pageerrors, "a genuine bug in the .then() chain "
                        "was swallowed along with guard()'s own rethrow")


if __name__ == "__main__":
    unittest.main()
