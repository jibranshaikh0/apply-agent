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

# Invented person; nothing here is real applicant data.
FAKE_PROFILE = {
    "first_name": "Test", "last_name": "Person", "full_name": "Test Person",
    "email": "test@example.invalid", "phone": "+1-555-0100",
    "current_company": "Example Co", "linkedin": "https://linkedin.invalid/in/test-person",
    "referral_source": "LinkedIn", "location_city": "Testville",
    "earliest_start_date": "2027-06-01", "work_authorization_us": "yes",
    "age_18_or_older": "yes", "custom_answers": {"why_this_company": "Fake motivation text."},
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


def _chromium_available() -> bool:
    if not HAVE_PLAYWRIGHT:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:
        return False


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright not installed")
class TestBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _chromium_available():
            raise unittest.SkipTest("chromium not available to playwright")
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
                self.assertTrue(fields)

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


if __name__ == "__main__":
    unittest.main()
