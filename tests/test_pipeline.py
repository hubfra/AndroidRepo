import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_data import BudgetExceeded, Builder, parse_statistics  # noqa: E402
from mock_api import MockApi  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class LimitedApi(MockApi):
    def __init__(self, config, limit):
        super().__init__(config)
        self.limit = limit

    def get(self, path, **params):
        if self.used >= self.limit:
            raise BudgetExceeded()
        return super().get(path, **params)


class PipelineTest(unittest.TestCase):
    def build(self, api, cache):
        return Builder(api, CONFIG, Path(cache)).build(date(2026, 11, 1))

    def test_full_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = MockApi(CONFIG)
            data = self.build(api, tmp)
            self.assertEqual([lg["name"] for lg in data["leagues"]],
                             [lg["name"] for lg in CONFIG["leagues"]])
            for lg in data["leagues"]:
                for m in lg["matches"]:
                    for side in ("home", "away"):
                        recent = m["recent"][side]
                        self.assertEqual(len(recent), CONFIG["recent_matches"])
                        dates = [r["date"] for r in recent]
                        self.assertEqual(dates, sorted(dates, reverse=True))
                        self.assertTrue(all(r["date"] < m["kickoff"] for r in recent))
                        self.assertTrue(all(r["stats"]["corners"] is not None for r in recent))
                    for h in m["h2h"]:
                        self.assertIsNotNone(h["stats"]["corners"]["home"])
            self.assertEqual(data["notes"], [])

            # Drugie uruchomienie korzysta z cache – tylko dzień + bieżące sezony.
            api2 = MockApi(CONFIG)
            self.build(api2, tmp)
            self.assertLessEqual(api2.used, 1 + len(CONFIG["leagues"]) * 3)

    def test_budget_exhausted_still_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.build(LimitedApi(CONFIG, 18), tmp)
            self.assertTrue(data["notes"])
            m = data["leagues"][0]["matches"][0]
            self.assertEqual(len(m["recent"]["home"]), CONFIG["recent_matches"])
            # Następnego dnia dobiera brakujące statystyki.
            data = self.build(MockApi(CONFIG), tmp)
            self.assertEqual(data["notes"], [])

    def test_parse_statistics(self):
        out = parse_statistics([{"team": {"id": 5}, "statistics": [
            {"type": "Corner Kicks", "value": 7}, {"type": "Offsides", "value": None},
            {"type": "Ball Possession", "value": "55%"}]}])
        self.assertEqual(out, {"5": {"Corner Kicks": 7, "Offsides": None, "Ball Possession": 55}})


if __name__ == "__main__":
    unittest.main()
