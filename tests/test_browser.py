"""Tests for the browser layer fixtures and (when Playwright is installed) E2E.

Static tests need only the stdlib. E2E tests skip cleanly without Playwright
or a Chromium build. Run: python -m unittest discover tests  (from the repo root)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(SRC))

import fill  # noqa: E402
import guard  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False

NAMES = ["greenhouse", "lever", "workday"]

# Invented person (tests/fixtures/fake_profile.json, also used by CI); no real applicant data.
FAKE_PROFILE = json.loads((FIXTURES / "fake_profile.json").read_text())


def _f(i, label, typ="text", options=()):
    return {"id": i, "label": label, "type": typ, "options": list(options)}


# What extract MUST return per fixture style (hand-written from the HTML, so a
# regression in label/type/option detection fails instead of passing vacuously).
EXPECTED_FIELDS = {
    "greenhouse": [_f("first_name", "First Name *"), _f("last_name", "Last Name *"), _f("email", "Email *"),
                   _f("phone", "Phone"), _f("resume", "Resume", "file"), _f("why_company", "Why this company?")],
    "lever": [_f("full_name", "Full name"), _f("email", "Email"), _f("phone", "Phone"),
              _f("org", "Current company"), _f("linkedin", "LinkedIn profile"),
              _f("source", "How did you hear about us?", "select", ["LinkedIn", "Company website", "Job board"])],
    "workday": [_f("work_auth", "Are you legally authorized to work in the United States?", "radio", ["Yes", "No"]),
                _f("age18", "Are you at least 18 years of age?", "checkbox"),
                _f("city", "City"), _f("start", "When are you available to start?")],
}


class FormScan(HTMLParser):
    """Splits a fixture into final-button text vs everything an ordinary field exposes."""

    def __init__(self):
        super().__init__()
        self.buttons: list[str] = []
        self.ordinary: list[str] = []
        self.controls = 0
        self._in_button = False

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self._in_button = True
            self.buttons.append("")
            return
        if tag in ("input", "select", "textarea"):
            self.controls += 1
        for k, v in attrs:
            if k in ("aria-label", "placeholder", "value", "name", "id") and v:
                self.ordinary.append(v)

    def handle_endtag(self, tag):
        if tag == "button":
            self._in_button = False

    def handle_data(self, data):
        if self._in_button:
            self.buttons[-1] += data
        elif data.strip():
            self.ordinary.append(data.strip())


def scan(name: str) -> FormScan:
    p = FormScan()
    p.feed((FIXTURES / f"{name}.html").read_text())
    p.close()
    return p


class TestFixturesStatic(unittest.TestCase):
    def test_fixtures_exist_and_parse(self):
        for name in NAMES:
            with self.subTest(fixture=name):
                self.assertTrue((FIXTURES / f"{name}.html").is_file())
                self.assertGreater(scan(name).controls, 0)

    def test_final_button_is_caught_by_guard(self):
        for name in NAMES:
            with self.subTest(fixture=name):
                buttons = scan(name).buttons
                self.assertTrue(any(guard.is_submit(b) for b in buttons), buttons)
                with self.assertRaises(guard.SubmitBlocked):
                    guard.assert_not_submit(next(b for b in buttons if guard.is_submit(b)))

    def test_ordinary_fields_do_not_trip_guard(self):
        for name in NAMES:
            for text in scan(name).ordinary:
                with self.subTest(fixture=name, text=text):
                    self.assertFalse(guard.is_submit(text))

    def test_fixtures_are_self_contained(self):
        for name in NAMES:
            html = (FIXTURES / f"{name}.html").read_text().lower()
            with self.subTest(fixture=name):
                for needle in ("http://", "https://", "<script", "<link", "src="):
                    self.assertNotIn(needle, html)


class TestStaticBehaviour(unittest.TestCase):
    def test_plan_fills_every_expected_field_with_fake_profile(self):
        """Every fixture field must be mapped, so E2E/CI fills genuinely exercise each control type."""
        for name, fields in EXPECTED_FIELDS.items():
            with self.subTest(fixture=name):
                plan = fill.build_fill_plan(fields, FAKE_PROFILE, use_model=False)
                self.assertEqual([i["field_id"] for i in plan["fills"]], [f["id"] for f in fields])
                self.assertEqual(plan["unmapped"], [])
                self.assertEqual(plan["missing_answers"], [])

    def test_verify_filled_catches_mismatch(self):
        plan = {"fills": [{"field_id": "email", "label": "Email", "value": "test@example.invalid"},
                          {"field_id": "city", "label": "City", "value": "Testville"}]}
        self.assertEqual(fill.verify_filled({"email": "test@example.invalid", "city": "Testville"}, plan), [])
        bad = fill.verify_filled({"email": "tes", "city": ""}, plan)
        self.assertEqual([(m["field_id"], m["expected"], m["actual"]) for m in bad],
                         [("email", "test@example.invalid", "tes"), ("city", "Testville", "")])

    def test_apply_fill_guard_blocks_before_touching_page(self):
        from unittest import mock
        import browser
        for label, attrs in [("Submit application", {}), ("Email", {"value": "Submit"}),
                             ("Email", {"aria-label": "Finalize"})]:
            with self.subTest(label=label, attrs=attrs):
                page = mock.MagicMock()
                el = page.locator.return_value.first
                el.get_attribute.side_effect = lambda k, a=attrs: a.get(k)
                el.evaluate.return_value = "INPUT"
                with self.assertRaises(guard.SubmitBlocked):
                    browser.apply_fill(page, {"id": "x", "label": label, "type": "text"}, "v")
                page.locator.return_value.fill.assert_not_called()
                page.locator.return_value.check.assert_not_called()

    def test_non_local_urls_refused(self):
        import browser
        for url in ["http://example.com/", "https://example.com/apply", "http://localhost.evil.com/",
                    "https://127.0.0.1.evil.com/", "http://127.0.0.1@evil.com/", "ftp://localhost/x",
                    "javascript:alert(1)", "//localhost/x", "http://10.0.0.1/", "http://[::1]/"]:
            with self.subTest(url=url):
                with self.assertRaises(SystemExit) as cm:
                    browser.check_local(url)
                self.assertIn("refused", str(cm.exception))
        for url in ["http://localhost:8000/x", "http://127.0.0.1:8765/a.html", "file:///tmp/a.html"]:
            with self.subTest(url=url):
                browser.check_local(url)

    def test_subrequest_filter(self):
        import browser
        for url in ["http://example.com/x.js", "https://203.0.113.1/p.png", "http://localhost.evil.com/"]:
            self.assertFalse(browser._is_local(url), url)
        for url in ["http://127.0.0.1:1/x", "file:///tmp/a.html", "data:text/plain,hi"]:
            self.assertTrue(browser._is_local(url), url)

    def test_cli_refuses_non_local_without_playwright(self):
        """check_local runs before the lazy playwright import, so this holds everywhere."""
        for argv in (["extract", "http://example.com/", "--out", os.devnull], ["fields", "https://example.com/"],
                     ["fill", "http://example.com/", "--plan", os.devnull, "--out", os.devnull]):
            with self.subTest(argv=argv):
                r = subprocess.run([sys.executable, str(SRC / "browser.py"), *argv],
                                   capture_output=True, text=True, timeout=60)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("refused", r.stderr)


def _chromium_available() -> bool:
    if not HAVE_PLAYWRIGHT:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


# CI sets this so a missing Playwright/Chromium is an error, not a silent skip.
REQUIRE_E2E = bool(os.environ.get("REQUIRE_BROWSER_E2E"))


class TestBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _chromium_available():
            msg = "playwright/chromium not available"
            if REQUIRE_E2E:
                raise RuntimeError(msg + " (REQUIRE_BROWSER_E2E is set)")
            raise unittest.SkipTest(msg)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.resume = os.path.join(cls.tmp.name, "resume.pdf")
        with open(cls.resume, "wb") as f:
            f.write(b"%PDF-1.4 fake resume\n")
        cls.profile = {**FAKE_PROFILE, "resume_path": cls.resume}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_browser(self, *args):
        return subprocess.run([sys.executable, str(SRC / "browser.py"), *args],
                              capture_output=True, text=True, timeout=120)

    def test_extract_plan_fill_verify(self):
        for name in NAMES:
            with self.subTest(fixture=name):
                url = (FIXTURES / f"{name}.html").as_uri()
                fields_path = os.path.join(self.tmp.name, f"{name}-fields.json")
                plan_path = os.path.join(self.tmp.name, f"{name}-plan.json")
                review_path = os.path.join(self.tmp.name, f"{name}-review.json")

                r = self.run_browser("extract", url, "--out", fields_path)
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(fields_path) as f:
                    fields = json.load(f)
                self.assertEqual(fields, EXPECTED_FIELDS[name])

                plan = fill.build_fill_plan(fields, self.profile, use_model=False)
                self.assertTrue(plan["stop_before_submit"])
                self.assertTrue(plan["fills"])
                with open(plan_path, "w") as f:
                    json.dump(plan, f)

                r = self.run_browser("fill", url, "--plan", plan_path, "--out", review_path)
                self.assertNotIn("SubmitBlocked", r.stderr)
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(review_path) as f:
                    review = json.load(f)
                self.assertTrue(review["stop_before_submit"])
                self.assertEqual(review["errors"], [])
                self.assertEqual(review["mismatches"], [])
                self.assertEqual(len(review["fills_applied"]), len(plan["fills"]))

    def test_second_pass_catches_value_the_page_did_not_retain(self):
        """mismatch.html truncates email to 3 chars on input; city is retained."""
        url = (FIXTURES / "mismatch.html").as_uri()
        plan = {"stop_before_submit": True, "fills": [
            {"field_id": "email", "label": "Email", "value": FAKE_PROFILE["email"]},
            {"field_id": "city", "label": "City", "value": FAKE_PROFILE["location_city"]}]}
        plan_path = os.path.join(self.tmp.name, "mismatch-plan.json")
        review_path = os.path.join(self.tmp.name, "mismatch-review.json")
        with open(plan_path, "w") as f:
            json.dump(plan, f)

        r = self.run_browser("fill", url, "--plan", plan_path, "--out", review_path)
        self.assertEqual(r.returncode, 1, r.stderr)  # mismatches make fill exit non-zero
        self.assertNotIn("SubmitBlocked", r.stderr)
        with open(review_path) as f:
            review = json.load(f)
        self.assertEqual([(m["field_id"], m["expected"], m["actual"]) for m in review["mismatches"]],
                         [("email", FAKE_PROFILE["email"], FAKE_PROFILE["email"][:3])])
        self.assertEqual(review["errors"], [])  # both fills were applied; only the second pass saw the loss
        self.assertEqual(len(review["fills_applied"]), 2)
        self.assertTrue(review["stop_before_submit"])

    def test_non_local_subrequests_are_aborted(self):
        """external.html pulls an image from TEST-NET-3; open_page's route must abort it."""
        import browser
        url = (FIXTURES / "external.html").as_uri()
        failed, finished = [], []
        with sync_playwright() as pw:
            real = pw.chromium.launch()
            new_page = real.new_page

            def watched_page():
                page = new_page()
                page.on("requestfailed", lambda req: failed.append(req.url))
                page.on("requestfinished", lambda req: finished.append(req.url))
                return page

            real.new_page = watched_page
            proxy = type("PW", (), {"chromium": type("C", (), {"launch": staticmethod(lambda: real)})})
            b, page = browser.open_page(proxy, url)
            try:
                fields = browser.extract_fields(page)
                broken = page.evaluate("() => { const i = document.getElementById('beacon'); "
                                       "return i.complete && i.naturalWidth === 0; }")
            finally:
                b.close()
        self.assertIn("http://203.0.113.1/pixel.png", failed)
        self.assertFalse([u for u in finished if "203.0.113." in u], finished)
        self.assertTrue(broken)
        self.assertEqual([f["id"] for f in fields], ["first_name"])  # the page itself still loaded


if __name__ == "__main__":
    unittest.main()
