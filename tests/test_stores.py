import argparse
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scanner import run, stores, watchlist
from scanner.expert_api import ONLINE_SHOP, ExpertApiError
from tests.recorded import BERLIN, FREITAL, RANGSDORF, TAUENTZIEN, fixture, recorded_api
from tests.test_expert_api import json_response

T0 = datetime(2026, 11, 23, 13, 40, tzinfo=timezone.utc)


class Dirs:
    def __init__(self, location=BERLIN, products=({"webcode": "11128346052"},)):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.config = root / "data", root / "config"
        self.data.mkdir()
        self.config.mkdir()
        if location is not None:
            run.write_json(self.config / "watchlist.json", {"location": location, "products": list(products)})

    def ctx(self, api, options=None, now=T0):
        return run.Context(api, self.data, "wifi", now, None, {}, config=self.config, options=options)

    def cleanup(self):
        self.tmp.cleanup()


class HaversineTest(unittest.TestCase):
    def test_distances_from_berlin(self):
        self.assertAlmostEqual(stores.haversine_km(52.5167, 13.4, 52.2974393, 13.4594041), 24.7, delta=0.1)
        self.assertAlmostEqual(stores.haversine_km(52.5167, 13.4, 51.013047, 13.6482026), 168.1, delta=0.1)
        self.assertEqual(stores.haversine_km(52.5, 13.4, 52.5, 13.4), 0.0)


class ParseTest(unittest.TestCase):
    def test_records_sorted_by_id_with_coordinates(self):
        records = stores.parse(fixture("storeFinder"))
        self.assertEqual([r["id"] for r in records], sorted(r["id"] for r in records))
        rangsdorf = next(r for r in records if r["id"] == RANGSDORF)
        self.assertEqual(rangsdorf, {"id": RANGSDORF, "expId": "32472581", "name": "ESC", "city": "Rangsdorf",
                                     "zip": "15834", "street": "Klein Kienitzer Straße 2", "lat": 52.2974393,
                                     "lng": 13.4594041, "online": False, "canUseShop": True, "decentralizedShop": True})

    def test_online_shop_and_distances(self):
        records = stores.with_distances(stores.parse(fixture("storeFinder")) + [stores.online_shop()], BERLIN)
        by_id = {r["id"]: r for r in records}
        self.assertEqual(by_id[ONLINE_SHOP]["name"], "Online-Shop")
        self.assertTrue(by_id[ONLINE_SHOP]["online"])
        self.assertIsNone(by_id[ONLINE_SHOP]["distanceKm"])
        self.assertEqual(by_id[RANGSDORF]["distanceKm"], 24.7)
        self.assertEqual(by_id[TAUENTZIEN]["distanceKm"], 4.3)
        self.assertEqual(by_id[FREITAL]["distanceKm"], 168.1)

    def test_without_location_no_distances(self):
        records = stores.with_distances(stores.parse(fixture("storeFinder")), {"lat": None, "lng": None})
        self.assertTrue(all(r["distanceKm"] is None for r in records))


class StepTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs()
        self.addCleanup(self.dirs.cleanup)

    def test_first_run_writes_the_file(self):
        api, transport, _ = recorded_api()
        summary = stores.step(self.dirs.ctx(api))
        self.assertEqual(summary, {"stores": 6, "before": None, "withinRadius": 2})
        data = run.read_json(self.dirs.data / "stores.json")
        self.assertEqual(data["updated"], "2026-11-23T13:40:00Z")
        self.assertEqual(data["count"], 6)
        self.assertEqual(data["location"], {**BERLIN, "lat": 52.5167, "lng": 13.4, "maxDistanceKm": 50.0})
        self.assertEqual(len(data["stores"]), 7)
        self.assertEqual(data["stores"][-1]["id"], ONLINE_SHOP)  # sorted: e_1907435 … e_36696318, then online
        self.assertEqual(transport.requests[0]["headers"]["Cookie"], f"fmarktcookie={ONLINE_SHOP}")
        self.assertEqual(len(api.calls), 1)

    def test_count_change_over_ten_percent_keeps_the_old_file_and_fails(self):
        api, _, _ = recorded_api()
        stores.step(self.dirs.ctx(api))
        old = (self.dirs.data / "stores.json").read_text()
        short = json_response(fixture("storeFinder")[:4])
        api, _, _ = recorded_api(storeFinder=[short])
        with self.assertRaises(ExpertApiError) as ctx:
            stores.step(self.dirs.ctx(api))
        self.assertIn("store count changed from 6 to 4", str(ctx.exception))
        self.assertEqual((self.dirs.data / "stores.json").read_text(), old)

    def test_force_accepts_the_new_count(self):
        api, _, _ = recorded_api()
        stores.step(self.dirs.ctx(api))
        api, _, _ = recorded_api(storeFinder=[json_response(fixture("storeFinder")[:4])])
        summary = stores.step(self.dirs.ctx(api, options={"force": True}))
        self.assertEqual(summary["stores"], 4)
        self.assertEqual(summary["before"], 6)
        self.assertEqual(run.read_json(self.dirs.data / "stores.json")["count"], 4)

    def test_small_change_is_accepted(self):
        api, _, _ = recorded_api(storeFinder=[json_response(fixture("storeFinder") * 10)])  # 60 "stores"
        stores.step(self.dirs.ctx(api))  # duplicate ids are fine for the count test
        api, _, _ = recorded_api(storeFinder=[json_response(fixture("storeFinder") * 10 + fixture("storeFinder")[:5])])
        self.assertEqual(stores.step(self.dirs.ctx(api))["stores"], 65)

    def test_empty_finder_fails(self):
        api, _, _ = recorded_api(storeFinder=[json_response([])])
        with self.assertRaises(ExpertApiError):
            stores.step(self.dirs.ctx(api))
        self.assertFalse((self.dirs.data / "stores.json").exists())

    def test_missing_watchlist_means_no_distances(self):
        dirs = Dirs(location=None)
        self.addCleanup(dirs.cleanup)
        api, _, _ = recorded_api()
        self.assertEqual(stores.step(dirs.ctx(api))["withinRadius"], 0)
        self.assertTrue(all(s["distanceKm"] is None for s in run.read_json(dirs.data / "stores.json")["stores"]))


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs()
        self.addCleanup(self.dirs.cleanup)
        api, _, _ = recorded_api()
        stores.step(self.dirs.ctx(api))

    def test_missing_file_is_none(self):
        self.assertIsNone(stores.load(Path(self.dirs.tmp.name) / "nowhere"))

    def test_same_location_keeps_the_stored_distances(self):
        records = stores.load(self.dirs.data, BERLIN)
        self.assertEqual(next(r["distanceKm"] for r in records if r["id"] == RANGSDORF), 24.7)

    def test_new_location_recomputes(self):
        freital = {"lat": 51.013047, "lng": 13.6482026, "maxDistanceKm": 50}
        records = stores.load(self.dirs.data, freital)
        self.assertEqual(next(r["distanceKm"] for r in records if r["id"] == FREITAL), 0.0)
        self.assertEqual(next(r["distanceKm"] for r in records if r["id"] == RANGSDORF), 143.4)


class WatchlistTest(unittest.TestCase):
    def test_webcode_from_url(self):
        url = "https://www.expert.de/shop/unsere-produkte/tv-audio/fernseher/11128346052-65oled951-oled-tv.html?branch_id=e_1"
        self.assertEqual(watchlist.parse_webcode(url), "11128346052")
        self.assertEqual(watchlist.parse_webcode(" 11128346052 "), "11128346052")
        self.assertEqual(watchlist.parse_webcode(11128346052), "11128346052")
        self.assertIsNone(watchlist.parse_webcode("https://www.expert.de/shop/"))
        self.assertIsNone(watchlist.parse_webcode(None))

    def test_defaults(self):
        wl = watchlist.normalize({"products": [{"url": "https://x/11128346052-a.html"}, {"webcode": "11128346052"}]})
        self.assertEqual(wl["location"], {"zip": None, "lat": None, "lng": None, "maxDistanceKm": 50.0})
        self.assertEqual(wl["products"], [{"webcode": "11128346052", "label": "11128346052", "targetPrice": None,
                                           "alertMode": "every", "watchSets": True, "role": "watch"}])

    def test_bad_entries(self):
        with self.assertRaises(watchlist.WatchlistError):
            watchlist.normalize({"products": [{"label": "no code"}]})
        with self.assertRaises(watchlist.WatchlistError):
            watchlist.normalize({"products": [{"webcode": "11128346052", "alertMode": "sometimes"}]})

    def test_repo_config_is_valid(self):
        wl = watchlist.load(Path(__file__).parent.parent / "config")
        self.assertEqual([p["webcode"] for p in wl["products"]], ["11128346052", "11128378730", "11128379730"])
        self.assertEqual(wl["location"]["zip"], "14167")
        self.assertEqual(wl["location"]["maxDistanceKm"], 100.0)


class CommandTest(unittest.TestCase):
    def test_run_step_prints_and_exits_0(self):
        dirs = Dirs()
        self.addCleanup(dirs.cleanup)
        api, _, _ = recorded_api()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.run_step(argparse.Namespace(data=str(dirs.data), force=False), "stores", now=T0, api=api,
                                ntfy=object(), env={})
        self.assertEqual(code, run.EXIT_OK)
        self.assertTrue(out.getvalue().startswith("stores ok · 1 calls · {"))
        self.assertTrue((dirs.data / "stores.json").exists())

    def test_run_step_reports_a_failed_step(self):
        dirs = Dirs()
        self.addCleanup(dirs.cleanup)
        api, _, _ = recorded_api(storeFinder=[json_response([])])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.run_step(argparse.Namespace(data=str(dirs.data), force=False), "stores", now=T0, api=api,
                                ntfy=object(), env={})
        self.assertEqual(code, run.EXIT_DEGRADED)
        self.assertIn("stores FAILED: store finder returned no stores", out.getvalue())

    def test_steps_are_registered(self):
        self.assertEqual(sorted(run.STEPS), ["cashback", "prices", "sets", "stores"])


if __name__ == "__main__":
    unittest.main()
