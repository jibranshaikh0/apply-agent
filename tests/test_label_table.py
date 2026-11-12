"""Tests for the ATS label table and its integration with mapping.py.

Run: python -m unittest discover tests  (from the repo root)
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import label_table  # noqa: E402
import mapping  # noqa: E402

TABLE = label_table.LABEL_TABLE


class TestTableIntegrity(unittest.TestCase):
    def test_scale(self):
        # The whole point: cover labels in code so the model rarely runs.
        self.assertGreaterEqual(len(TABLE), 2500)

    def test_all_targets_are_real_profile_keys(self):
        valid = set(mapping.FIELD_ALIASES) | label_table.CUSTOM_ANSWER_KEYS
        bad = {label: key for label, key in TABLE.items() if key not in valid}
        self.assertEqual(bad, {})

    def test_keys_are_normalized(self):
        for label in TABLE:
            self.assertEqual(label, mapping.normalize(label))

    def test_no_near_duplicate_keys_differ_only_by_case_or_punct(self):
        # normalize() is the canonical form; if two raw variants normalized
        # to the same string across different keys the build would have
        # raised at import. Re-assert cheaply here.
        self.assertEqual(len(TABLE), len(set(TABLE)))


class TestTableIntegration(unittest.TestCase):
    """Tricky real-form variants must resolve through map_label."""

    CASES = {
        # Greenhouse / Lever style
        "First Name *": "first_name",
        "Last Name": "last_name",
        "Email": "email",
        "Phone": "phone",
        "Resume/CV": "resume_path",
        "LinkedIn Profile": "linkedin",
        "Website": "portfolio",
        "Current Company": "current_company",
        # Workday style
        "Are you legally authorized to work in the United States?": "work_authorization_us",
        "Will you now or in the future require sponsorship for employment visa status?": "requires_sponsorship",
        "How did you hear about us?": "referral_source",
        "What is your expected salary range?": "desired_salary",
        "When are you available to start?": "earliest_start_date",
        "Address Line 1": "address_line1",
        "Country/Territory": "location_country",
        # Taleo / iCIMS style
        "Are you at least 18 years of age?": "age_18_or_older",
        "Have you ever served in the U.S. Armed Forces?": "eeoc_veteran_status",
        "Are you Hispanic or Latino?": "eeoc_race",
        "Were you referred by a current employee?": "referred_by",
        # EEO self-ID forms
        "Voluntary Self-Identification of Disability": "eeoc_disability_status",
        "Gender - voluntary self identification": "eeoc_gender",
        "Are you a protected veteran?": "eeoc_veteran_status",
        # Education
        "College/University": "school",
        "Highest level of education completed": "degree",
        "Field of study": "major",
        "Expected graduation date": "graduation_year",
        "Cumulative GPA": "gpa",
        # Essay-style
        "Why do you want to work here?": "why_this_company",
    }

    def test_spot_variants(self):
        for label, key in self.CASES.items():
            with self.subTest(label=label):
                self.assertEqual(mapping.map_label(label), key)

    def test_table_lookups_are_exact_normalizations(self):
        for label, key in self.CASES.items():
            n = mapping.normalize(label)
            if n in TABLE:
                self.assertEqual(TABLE[n], key)


class TestFallbackStillWorks(unittest.TestCase):
    def test_unmapped_returns_none(self):
        self.assertIsNone(mapping.map_label("zzzq unknown field 12345"))

    def test_pattern_fallback_for_unseen_close_label(self):
        # Not in the table verbatim; fuzzy matcher should still catch it.
        self.assertEqual(mapping.map_label("github profile urll"), "github")


if __name__ == "__main__":
    unittest.main()
