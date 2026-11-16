"""Unit tests for the cleaning rules in scripts/etl_pipeline.py.

They need no database: importing the module only loads the district registry.
Run with:  python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import etl_pipeline as etl  # noqa: E402


class ResolveDistrictTest(unittest.TestCase):
    def test_exact_name_keeps_its_state(self):
        self.assertEqual(etl.resolve_district("Pune", "Maharashtra"), ("Pune", "Maharashtra"))

    def test_case_and_whitespace_are_ignored(self):
        self.assertEqual(etl.resolve_district("  PUNE ", "MAHARASHTRA"), ("Pune", "Maharashtra"))

    def test_name_without_its_bracket_part(self):
        self.assertEqual(etl.resolve_district("Bellary", "Karnataka"),
                         ("Ballari (Bellary)", "Karnataka"))

    def test_official_rename_uses_the_alias_list(self):
        self.assertEqual(etl.resolve_district("Prayagraj", "Uttar Pradesh"),
                         ("Allahabad", "Uttar Pradesh"))
        self.assertEqual(etl.resolve_district("Gurugram", "Haryana"), ("Gurgaon", "Haryana"))

    def test_single_letter_typo_is_fuzzy_matched(self):
        self.assertEqual(etl.resolve_district("Ahmedabd", "Gujarat"), ("Ahmedabad", "Gujarat"))

    def test_same_name_in_two_states_stays_separate(self):
        self.assertEqual(etl.resolve_district("Aurangabad", "Bihar"), ("Aurangabad", "Bihar"))
        self.assertEqual(etl.resolve_district("Aurangabad", "Maharashtra"),
                         ("Aurangabad", "Maharashtra"))

    def test_ambiguous_name_without_a_state_is_not_guessed(self):
        self.assertIsNone(etl.resolve_district("Aurangabad", ""))

    def test_unique_name_is_found_without_a_state(self):
        self.assertEqual(etl.resolve_district("Pune", ""), ("Pune", "Maharashtra"))

    def test_unknown_name_is_rejected(self):
        self.assertIsNone(etl.resolve_district("Not A Real District", "Gujarat"))

    def test_every_registry_district_resolves_to_itself(self):
        for district, state in etl.ALL_DISTRICTS:
            self.assertEqual(etl.resolve_district(district, state), (district, state))


class DateParsingTest(unittest.TestCase):
    def test_month_accepts_four_formats(self):
        for raw in ("2023-03", "Mar-2023", "01/03/2023", "2023/03/01"):
            parsed = etl.parse_month(raw)
            self.assertEqual((parsed.year, parsed.month), (2023, 3), raw)

    def test_bad_month_is_not_a_date(self):
        self.assertTrue(etl.parse_month("soon") is etl.pd.NaT)

    def test_quarter_formats(self):
        self.assertEqual(etl.parse_quarter("2024Q3"), (2024, 3))
        self.assertEqual(etl.parse_quarter("2024-Q3"), (2024, 3))
        self.assertEqual(etl.parse_quarter("third"), (None, None))

    def test_financial_year_formats(self):
        self.assertEqual(etl.parse_fy("2022-23"), 2022)
        self.assertEqual(etl.parse_fy("2022"), 2022)


if __name__ == "__main__":
    unittest.main()
