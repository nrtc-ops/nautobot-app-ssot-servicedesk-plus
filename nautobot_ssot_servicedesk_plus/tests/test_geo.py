"""Unit tests for the site-name -> US state parser (no DB required)."""

import unittest

from nautobot_ssot_servicedesk_plus.utils.geo import parse_state


class ParseStateTests(unittest.TestCase):
    def test_trailing_abbreviation_with_comma(self):
        self.assertEqual(parse_state("Dallas, TX"), "TX")

    def test_trailing_abbreviation_with_space(self):
        self.assertEqual(parse_state("Anchorage AK"), "AK")

    def test_double_space_variant(self):
        self.assertEqual(parse_state("Abbeville  SC"), "SC")

    def test_full_state_name(self):
        self.assertEqual(parse_state("Denver, Colorado"), "CO")

    def test_parenthetical_suffix(self):
        self.assertEqual(parse_state("Windhorst, TX (Wichita Falls Headend)"), "TX")

    def test_unparseable_returns_none(self):
        for name in ("Border2Border", "Signal House", "Test", ""):
            self.assertIsNone(parse_state(name))

    def test_none_input(self):
        self.assertIsNone(parse_state(None))


if __name__ == "__main__":
    unittest.main()
