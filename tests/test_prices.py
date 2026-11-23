import unittest
from datetime import datetime, timedelta, timezone

from scanner import expert_api, prices, run, stores
from scanner.expert_api import ONLINE_SHOP, ExpertApiError, ScanAborted
from tests.recorded import (BERLIN, FREITAL, PASTERNAK, PHILIPS, RANGSDORF, SONY65, TAUENTZIEN, fixture,
                            pricepds_key, recorded_api)
from tests.test_expert_api import SERVER_ERROR, json_response
from tests.test_stores import Dirs

T0 = datetime(2026, 11, 23, 13, 40, tzinfo=timezone.utc)  # 14:40 Berlin
PHILIPS_IMAGE = "https://cdn.expert.de/05/15/c6/920de71061c0d6d0712317e7a4f1f69678/Abbildung_2663599.png.png"


def failing():
    return [json_response(SERVER_ERROR, 500)]


class PricesTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs(products=({"webcode": PHILIPS, "label": "Philips 65OLED951"},))
        self.addCleanup(self.dirs.cleanup)

    def scan(self, now=T0, **overrides):
        api, transport, _ = recorded_api(**overrides)
        summary = prices.step(self.dirs.ctx(api, now=now))
        return summary, api, transport

    def product(self, webcode=PHILIPS):
        return run.read_json(self.dirs.data / "products" / f"{webcode}.json")

    def test_first_scan_refreshes_the_stores_and_writes_the_product(self):
        summary, api, transport = self.scan()
        self.assertEqual(summary, {"products": 1, "withOffer": 3, "unknown": 0, "incomplete": [], "articleErrors": {}})
        self.assertTrue((self.dirs.data / "stores.json").exists())
        self.assertEqual(len(api.calls), 1 + 2 + 7)  # finder, article + medium, 6 stores + online
        p = self.product()
        self.assertEqual((p["webcode"], p["label"], p["articleId"], p["name"], p["brand"], p["brandId"]),
                         (PHILIPS, "Philips 65OLED951", "e_977673", "65OLED951 OLED TV", "Philips", "e_443"))
        self.assertEqual(p["image"], PHILIPS_IMAGE)
        self.assertEqual(p["url"], "https://www.expert.de/shop/unsere-produkte/tv-audio/fernseher/lcd-led-fernseher/"
                                   "11128346052-65oled951-oled-tv.html")
        self.assertEqual((p["targetPrice"], p["alertMode"], p["watchSets"], p["role"]), (None, "every", True, "watch"))
        self.assertEqual(p["lastScan"], "2026-11-23T13:40:00Z")
        self.assertEqual([o["storeId"] for o in p["offers"]], [FREITAL, ONLINE_SHOP, RANGSDORF])

    def test_offers_and_totals(self):
        self.scan()
        offers = {o["storeId"]: o for o in self.product()["offers"]}
        online = offers[ONLINE_SHOP]
        self.assertEqual((online["price"], online["shipping"], online["codeDiscount"], online["codeTitle"]),
                         (2359, 79.9, 10, "sofort-rabatt · 10€ Rabatt mit WERO10"))
        self.assertEqual((online["onlineStock"], online["storeStock"], online["displayType"]), (1, 0, None))
        self.assertEqual((online["totalShipped"], online["totalPickup"], online["distanceKm"]), (2428.9, None, None))
        self.assertEqual((online["cacheLevel"], online["cachedOn"]), ("MOST_RECENT", "2026-11-23T12:09:34Z"))
        rangsdorf = offers[RANGSDORF]
        self.assertEqual((rangsdorf["price"], rangsdorf["displayType"], rangsdorf["distanceKm"]), (2095, "Aussteller", 24.7))
        self.assertEqual((rangsdorf["totalShipped"], rangsdorf["totalPickup"]), (2174.9, 2095))
        freital = offers[FREITAL]
        self.assertEqual((freital["price"], freital["onlineStock"], freital["storeStock"]), (2699, 0, 1))
        self.assertEqual((freital["totalShipped"], freital["totalPickup"]), (None, None))  # not shipped, 168 km away
        self.assertNotIn(PASTERNAK, offers)

    def test_best_shipped_and_pickup(self):
        self.scan()
        best = self.product()["best"]
        self.assertEqual(best["shipped"], {"storeId": RANGSDORF, "total": 2174.9, "price": 2095, "distanceKm": 24.7,
                                           "displayType": "Aussteller", "shipping": 79.9, "codeDiscount": 0})
        self.assertEqual(best["pickup"], {"storeId": RANGSDORF, "total": 2095, "price": 2095, "distanceKm": 24.7,
                                          "displayType": "Aussteller"})

    def test_scan_block_records_cache_levels(self):
        self.scan()
        s = self.product()["scan"]
        self.assertEqual(s, {"time": "2026-11-23T13:40:00Z", "stores": 7, "withOffer": 3, "failed": 0, "unknown": 0,
                             "vanished": 0, "dropped": 0, "incomplete": False, "retried": False,
                             "cacheLevels": {"MOST_RECENT": 3}})

    def test_history_point_per_berlin_day_keeps_the_days_minimum(self):
        self.scan()
        self.assertEqual(self.product()["history"], [{"date": "2026-11-23", "shipped": 2174.9, "pickup": 2095}])
        dearer = dict(fixture("pricepds-philips-rangsdorf"))
        dearer["price"] = {**dearer["price"], "bruttoPrice": 2195}
        self.scan(now=T0 + timedelta(hours=2), **{pricepds_key(PHILIPS, RANGSDORF): [json_response(dearer)]})
        self.assertEqual(self.product()["history"], [{"date": "2026-11-23", "shipped": 2174.9, "pickup": 2095}])
        self.assertEqual(self.product()["best"]["pickup"]["total"], 2195)
        self.scan(now=T0 + timedelta(hours=9), **{pricepds_key(PHILIPS, RANGSDORF): [json_response(dearer)]})  # 23:40 Berlin, 24 Nov? no: 22:40
        self.scan(now=T0 + timedelta(hours=10), **{pricepds_key(PHILIPS, RANGSDORF): [json_response(dearer)]})  # 00:40 on 24 Nov
        self.assertEqual([p["date"] for p in self.product()["history"]], ["2026-11-23", "2026-11-24"])
        self.assertEqual(self.product()["history"][1], {"date": "2026-11-24", "shipped": 2274.9, "pickup": 2195})

    def test_history_is_capped_at_90_days(self):
        self.scan()
        p = self.product()
        p["history"] = [{"date": f"2026-{m:02d}-{d:02d}", "shipped": 1, "pickup": None}
                        for m in range(1, 7) for d in range(1, 29)][:100]
        run.write_json(self.dirs.data / "products" / f"{PHILIPS}.json", p)
        self.scan(now=T0 + timedelta(hours=1))
        history = self.product()["history"]
        self.assertEqual(len(history), 90)
        self.assertEqual(history[-1]["date"], "2026-11-23")

    def test_failed_call_keeps_the_previous_offer_as_unknown(self):
        self.scan()
        summary, _, _ = self.scan(now=T0 + timedelta(hours=2), **{pricepds_key(PHILIPS, RANGSDORF): failing()})
        self.assertEqual((summary["withOffer"], summary["unknown"], summary["incomplete"]), (2, 1, []))
        p = self.product()
        kept = next(o for o in p["offers"] if o["storeId"] == RANGSDORF)
        self.assertEqual((kept["unknown"], kept["unknownSince"], kept["unknownReason"], kept["price"]),
                         (True, "2026-11-23T15:40:00Z", "failed", 2095))
        self.assertEqual(kept["seen"], "2026-11-23T13:40:00Z")
        self.assertEqual(p["best"]["pickup"]["storeId"], RANGSDORF)
        self.assertTrue(p["best"]["pickup"]["unknown"])
        self.assertEqual(p["scan"], {"time": "2026-11-23T15:40:00Z", "stores": 7, "withOffer": 2, "failed": 1,
                                     "unknown": 1, "vanished": 1, "dropped": 0, "incomplete": False,
                                     "retried": False, "cacheLevels": {"MOST_RECENT": 2}})

    def test_thin_body_without_price_keeps_the_previous_offer(self):
        self.scan()
        thin = {"articleId": "e_977673", "webcode": PHILIPS, "store": RANGSDORF, "price": {"cacheLevel": "MOST_RECENT"}}
        self.scan(now=T0 + timedelta(hours=2), **{pricepds_key(PHILIPS, RANGSDORF): [json_response(thin)]})
        kept = next(o for o in self.product()["offers"] if o["storeId"] == RANGSDORF)
        self.assertEqual((kept["unknown"], kept["unknownReason"]), (True, "missing"))

    def test_unknown_offer_is_dropped_after_24_hours_and_unknown_since_sticks(self):
        self.scan()
        gone = {pricepds_key(PHILIPS, RANGSDORF): failing()}
        self.scan(now=T0 + timedelta(hours=2), **gone)
        self.scan(now=T0 + timedelta(hours=4), **gone)
        kept = next(o for o in self.product()["offers"] if o["storeId"] == RANGSDORF)
        self.assertEqual(kept["unknownSince"], "2026-11-23T15:40:00Z")
        self.assertEqual(self.product()["scan"]["vanished"], 0)  # it was unknown already, not a new loss
        self.scan(now=T0 + timedelta(hours=26), **gone)
        p = self.product()
        self.assertNotIn(RANGSDORF, [o["storeId"] for o in p["offers"]])
        self.assertEqual((p["scan"]["unknown"], p["scan"]["dropped"]), (0, 1))
        self.assertEqual(p["best"]["shipped"]["storeId"], ONLINE_SHOP)
        self.assertIsNone(p["best"]["pickup"])

    def test_offer_that_comes_back_clears_the_flag(self):
        self.scan()
        self.scan(now=T0 + timedelta(hours=2), **{pricepds_key(PHILIPS, RANGSDORF): failing()})
        self.scan(now=T0 + timedelta(hours=4))
        back = next(o for o in self.product()["offers"] if o["storeId"] == RANGSDORF)
        self.assertNotIn("unknown", back)
        self.assertNotIn("unknownSince", back)
        self.assertEqual(back["seen"], "2026-11-23T17:40:00Z")

    def test_more_than_half_vanished_is_incomplete(self):
        self.scan()
        gone = {pricepds_key(PHILIPS, RANGSDORF): failing(), pricepds_key(PHILIPS, FREITAL): failing()}
        summary, _, _ = self.scan(now=T0 + timedelta(hours=2), **gone)
        self.assertEqual(summary["incomplete"], [PHILIPS])
        self.assertTrue(self.product()["scan"]["incomplete"])
        self.assertEqual(self.product()["scan"]["vanished"], 2)
        self.assertEqual(len(self.product()["offers"]), 3)  # the two kept, plus online

    def test_half_vanished_is_not_incomplete(self):
        self.scan()
        self.scan(now=T0 + timedelta(hours=2), **{pricepds_key(PHILIPS, RANGSDORF): failing()})
        self.assertFalse(self.product()["scan"]["incomplete"])

    def test_article_failure_is_noted_and_retried_next_scan(self):
        summary, api, _ = self.scan(**{f"search/article?webcode={PHILIPS}": failing()})
        self.assertEqual(summary["articleErrors"], {PHILIPS: "GET /api/search/article: HTTP 500 after 3 retries"})
        p = self.product()
        self.assertEqual((p["name"], p["image"]), (None, None))
        self.assertEqual(p["articleError"], "GET /api/search/article: HTTP 500 after 3 retries")
        self.assertEqual(len(p["offers"]), 3)
        summary, api, _ = self.scan(now=T0 + timedelta(hours=2))
        self.assertEqual(summary["articleErrors"], {})
        self.assertEqual(self.product()["name"], "65OLED951 OLED TV")
        self.assertNotIn("articleError", self.product())

    def test_article_is_fetched_once(self):
        self.scan()
        _, api, _ = self.scan(now=T0 + timedelta(hours=2))
        self.assertEqual([c["endpoint"] for c in api.calls if "pricepds" not in c["endpoint"]], [])

    def test_config_changes_update_the_product(self):
        self.scan()
        run.write_json(self.dirs.config / "watchlist.json", {"location": BERLIN, "products": [
            {"webcode": PHILIPS, "label": "Philips", "targetPrice": 1999, "alertMode": "target"}]})
        self.scan(now=T0 + timedelta(hours=2))
        p = self.product()
        self.assertEqual((p["label"], p["targetPrice"], p["alertMode"]), ("Philips", 1999, "target"))

    def test_two_products_two_files(self):
        run.write_json(self.dirs.config / "watchlist.json", {"location": BERLIN, "products": [
            {"webcode": PHILIPS}, {"webcode": SONY65, "label": "Sony 65"}]})
        summary, api, _ = self.scan()
        self.assertEqual((summary["products"], summary["withOffer"]), (2, 4))
        sony = self.product(SONY65)
        self.assertEqual((sony["name"], sony["brand"], sony["articleId"]), ("K65XR95M2PB BRAVIA 9 II True RGB TV", "Sony", "e_973660"))
        self.assertEqual(sony["best"]["shipped"], {"storeId": ONLINE_SHOP, "total": 3459, "price": 3469, "distanceKm": None,
                                                   "displayType": None, "shipping": 0, "codeDiscount": 10})
        self.assertIsNone(sony["best"]["pickup"])
        self.assertEqual(len(api.calls), 1 + 2 * 2 + 2 * 7)

    def test_pickup_needs_the_radius(self):
        run.write_json(self.dirs.config / "watchlist.json", {"location": {**BERLIN, "maxDistanceKm": 20},
                                                             "products": [{"webcode": PHILIPS}]})
        self.scan()
        p = self.product()
        self.assertIsNone(p["best"]["pickup"])
        self.assertEqual(p["best"]["shipped"]["storeId"], RANGSDORF)

    def test_missing_watchlist_fails_the_step(self):
        dirs = Dirs(location=None)
        self.addCleanup(dirs.cleanup)
        api, _, _ = recorded_api()
        with self.assertRaises(ExpertApiError) as ctx:
            prices.step(dirs.ctx(api))
        self.assertIn("watchlist.json is missing", str(ctx.exception))

    def test_empty_watchlist_fails_the_step(self):
        dirs = Dirs(products=())
        self.addCleanup(dirs.cleanup)
        api, _, _ = recorded_api()
        with self.assertRaises(ExpertApiError):
            prices.step(dirs.ctx(api))

    def test_stores_file_is_reused(self):
        api, _, _ = recorded_api()
        stores.step(self.dirs.ctx(api))
        _, api, _ = self.scan()
        self.assertEqual([c["endpoint"] for c in api.calls][:1], ["/api/search/article"])


class AbortRetryTest(unittest.TestCase):
    """A burst of 500s aborts a product's sweep; the step waits and tries the product once more."""

    def setUp(self):
        self.dirs = Dirs(products=({"webcode": PHILIPS},))
        self.addCleanup(self.dirs.cleanup)
        self.sleeps = []
        self.saved = (expert_api.ABORT_MIN_CALLS, prices.SLEEP)
        expert_api.ABORT_MIN_CALLS, prices.SLEEP = 5, self.sleeps.append

    def tearDown(self):
        expert_api.ABORT_MIN_CALLS, prices.SLEEP = self.saved

    def test_second_try_succeeds(self):
        burst = [json_response(SERVER_ERROR, 500)] * 4  # four attempts fail, then the recorded answer
        api, _, _ = recorded_api(**{pricepds_key(PHILIPS, RANGSDORF): burst + [json_response(fixture("pricepds-philips-rangsdorf"))],
                                    pricepds_key(PHILIPS, FREITAL): burst + [json_response(fixture("pricepds-philips-freital"))]})
        summary = prices.step(self.dirs.ctx(api))
        self.assertEqual(self.sleeps, [prices.ABORT_RETRY_PAUSE])
        self.assertEqual(summary["withOffer"], 3)
        p = run.read_json(self.dirs.data / "products" / f"{PHILIPS}.json")
        self.assertTrue(p["scan"]["retried"])
        self.assertEqual(p["scan"]["failed"], 0)

    def test_second_abort_ends_the_run(self):
        api, _, _ = recorded_api(**{pricepds_key(PHILIPS, RANGSDORF): failing(), pricepds_key(PHILIPS, FREITAL): failing()})
        with self.assertRaises(ScanAborted):
            prices.step(self.dirs.ctx(api))
        self.assertEqual(self.sleeps, [prices.ABORT_RETRY_PAUSE])
        self.assertFalse((self.dirs.data / "products" / f"{PHILIPS}.json").exists())


class HelpersTest(unittest.TestCase):
    def test_brand_from_headline(self):
        self.assertEqual(prices.brand_from("Philips 65OLED951 OLED TV (65 Zoll)", "65OLED951 OLED TV"), "Philips")
        self.assertIsNone(prices.brand_from("65OLED951 OLED TV", "65OLED951 OLED TV"))
        self.assertIsNone(prices.brand_from(None, "x"))
        self.assertIsNone(prices.brand_from("Sony other", "65OLED951"))

    def test_best_prefers_known_then_nearer_at_equal_totals(self):
        offers = {
            "e_1": {"storeId": "e_1", "totalShipped": 100, "totalPickup": 100, "price": 100, "distanceKm": 30, "displayType": None, "shipping": 0, "codeDiscount": 0, "unknown": True},
            "e_2": {"storeId": "e_2", "totalShipped": 100, "totalPickup": 100, "price": 100, "distanceKm": 40, "displayType": None, "shipping": 0, "codeDiscount": 0},
            "e_3": {"storeId": "e_3", "totalShipped": 100, "totalPickup": 100, "price": 100, "distanceKm": 10, "displayType": None, "shipping": 0, "codeDiscount": 0},
        }
        best = prices.best_offers(offers)
        self.assertEqual(best["pickup"]["storeId"], "e_3")
        self.assertNotIn("unknown", best["pickup"])
        self.assertEqual(prices.best_offers({}), {"shipped": None, "pickup": None})

    def test_update_history_merges_nulls(self):
        h = prices.update_history([{"date": "2026-11-23", "shipped": None, "pickup": 5}], "2026-11-23",
                                  {"shipped": {"total": 7}, "pickup": None})
        self.assertEqual(h, [{"date": "2026-11-23", "shipped": 7, "pickup": 5}])


if __name__ == "__main__":
    unittest.main()
