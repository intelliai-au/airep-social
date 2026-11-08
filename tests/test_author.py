"""author.py's planning and brief rendering, without the SDK, git or a network."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import author  # noqa: E402
import schedule  # noqa: E402


class PlanningTests(unittest.TestCase):
    def test_missing_days_cover_the_month_after_next_and_skip_what_exists(self) -> None:
        have = {date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)}
        days = author.missing_days(have, date(2026, 11, 8))
        self.assertEqual(days[0], date(2026, 11, 24))  # the next unwritten Tuesday
        self.assertEqual(days[-1], date(2027, 1, 28))  # last Thursday of January
        self.assertTrue(all(schedule.allowed_slots(d) for d in days))
        self.assertNotIn(date(2026, 11, 17), days)
        # Christmas keeps Tuesdays only: 22 and 29 Dec, nothing on 23/24 or 30/31.
        december = [d for d in days if d.month == 12 and d.day >= 22]
        self.assertEqual(december, [date(2026, 12, 22), date(2026, 12, 29)])

    def test_past_days_are_never_written(self) -> None:
        days = author.missing_days(set(), date(2026, 12, 10))
        self.assertTrue(all(d > date(2026, 12, 10) for d in days))

    def test_by_month_keeps_order(self) -> None:
        groups = author.by_month(author.missing_days(set(), date(2026, 11, 8)))
        self.assertEqual(list(groups), [(2026, 11), (2026, 12), (2027, 1)])

    def test_add_months_wraps_the_year(self) -> None:
        self.assertEqual(author.add_months(date(2026, 11, 8), 2), (2027, 1))
        self.assertEqual(author.add_months(date(2027, 12, 1), 1), (2028, 1))


class YearTableTests(unittest.TestCase):
    def test_year_md_parses_every_plan_month(self) -> None:
        rows = author.year_rows(author.YEAR_MD.read_text())
        self.assertIn((2027, 2), rows)
        self.assertIn("BAS", rows[(2027, 2)].theme)
        self.assertIn("28 Feb", rows[(2027, 2)].hooks)
        self.assertEqual(len([k for k in rows if k[0] == 2027]), 11)

    def test_existing_films_are_named_for_the_first_three_months(self) -> None:
        rows = author.year_rows(author.YEAR_MD.read_text())
        for key in ((2026, 11), (2026, 12), (2027, 1)):
            self.assertIn("(existing)", rows[key].films)
        self.assertNotIn("(existing)", rows[(2027, 2)].films)

    def test_month_outside_the_table_still_briefs(self) -> None:
        brief = author.month_brief(2028, 3, year_text="")
        self.assertEqual(brief.name, "March 2028")
        self.assertIn("docs/YEAR.md", brief.theme)


class BriefTests(unittest.TestCase):
    def test_write_brief_names_the_dates_theme_and_python(self) -> None:
        brief = author.month_brief(2026, 12)
        days = [d for d in schedule.cadence() if d.month == 12 and d.year == 2026]
        text = author.render_brief(
            "write",
            brief,
            days,
            python="/opt/venv/bin/python",
            films_present=["airep_quote_to_invoice_music.mp4", "airep_payment_music.mp4"],
        )
        self.assertIn("December 2026", text)
        self.assertIn("2026-12-22", text)
        self.assertIn("Get paid before the break", text)
        self.assertIn('"/opt/venv/bin/python" build.py', text)
        self.assertIn("first and third Tuesday", text)  # both films exist
        self.assertNotIn("$", text)  # every placeholder filled

    def test_write_brief_falls_back_to_images_when_films_are_missing(self) -> None:
        brief = author.month_brief(2027, 2)
        days = [d for d in schedule.cadence() if (d.year, d.month) == (2027, 2)]
        text = author.render_brief("write", brief, days, python="python3", films_present=[])
        self.assertIn("EVERY Tuesday as a feature image", text)

    def test_film_brief_names_the_month_and_films(self) -> None:
        brief = author.month_brief(2027, 2)
        text = author.render_brief("film", brief, [], python="python3", films_present=[])
        self.assertIn("February 2027", text)
        self.assertIn("three-way match", text)
        self.assertIn("content/2027-02-*-feature-*.yaml", text)


class EnvTests(unittest.TestCase):
    def test_credentials_are_blanked_and_the_api_key_always_is(self) -> None:
        env = author.env_overrides(
            {"HOME": "/h", "GITHUB_TOKEN": "x", "ANTHROPIC_API_KEY": "k", "PGPASSWORD": "p"}
        )
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(env["GITHUB_TOKEN"], "")
        self.assertEqual(env["PGPASSWORD"], "")
        self.assertNotIn("HOME", env)
        self.assertEqual(env["DISABLE_AUTOUPDATER"], "1")

    def test_api_key_blanked_even_when_absent(self) -> None:
        self.assertEqual(author.env_overrides({})["ANTHROPIC_API_KEY"], "")


class DryRunTests(unittest.TestCase):
    def test_dry_run_prints_briefs_and_starts_nothing(self) -> None:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = author.main(
                ["write", "--dry-run", "--today", "2026-11-08", "--python", "python3"]
            )
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("December 2026", text)
        self.assertIn("January 2027", text)
        self.assertIn("# Write the AIREP social posts for December 2026", text)

    def test_today_requires_dry_run(self) -> None:
        with self.assertRaises(SystemExit):
            author.main(["write", "--today", "2026-11-08"])


if __name__ == "__main__":
    unittest.main()
