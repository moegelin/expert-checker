import unittest
from datetime import datetime, timezone

from scanner import alerts, run, sets
from scanner.expert_api import ONLINE_SHOP
from tests.recorded import BERLIN, PHILIPS, RANGSDORF, SONY65, TAUENTZIEN, fixture, recorded_api
from tests.test_expert_api import SERVER_ERROR, json_response
from tests.test_run import FakeNtfy
from tests.test_stores import Dirs

T0 = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
SONY_ARTICLE = "e_973660"


def product(webcode=SONY65, article=SONY_ARTICLE, offers=None, sets_=None):
    return {"webcode": webcode, "label": "Sony BRAVIA 9 II 65\"", "articleId": article,
            "url": f"https://www.expert.de/shop/{webcode}-x.html", "lastScan": run.iso(T0), "offers": offers or [],
            "sets": sets_ or []}


def offer(store_id, price, distance=None):
    return {"storeId": store_id, "price": price, "distanceKm": distance, "totalShipped": price, "totalPickup": None}


class ParseTest(unittest.TestCase):
    def test_sony_set_with_theatre_bar(self):
        deals = sets.parse_bundles(fixture("bundles-sony65-online"), SONY_ARTICLE)
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertEqual((d["bundleId"], d["promotionId"], d["discount"]), ("20000083", "e_4205", 100))
        self.assertEqual((d["unpromoted"], d["promoted"]), (3888, 3788))
        self.assertEqual(d["accessory"], "BRAVIA Theatre Bar 6 schwarz Soundbar mit Subwoofer")
        self.assertEqual((d["articleIds"], d["accessoryIds"]), ([SONY_ARTICLE, "e_943283"], ["e_943283"]))
        self.assertEqual((d["validFrom"], d["validTo"]), ("01.11.2026", "30.11.2026"))

    def test_bundles_without_a_discount_and_warranties_are_no_deals(self):
        self.assertEqual(sets.parse_bundles(fixture("bundles-philips-online"), "e_977673"), [])

    def test_empty_and_odd_bodies(self):
        self.assertEqual(sets.parse_bundles(None, SONY_ARTICLE), [])
        self.assertEqual(sets.parse_bundles({}, SONY_ARTICLE), [])
        self.assertEqual(sets.parse_bundles({"bundles": [{"id": 1, "discounts": [{"discount": {"gross": -5}}]}]}, "x"), [])


class StepTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs(products=({"webcode": SONY65, "label": "Sony"}, {"webcode": PHILIPS, "label": "Philips", "watchSets": False}))
        self.addCleanup(self.dirs.cleanup)

    def write(self, rec):
        run.write_json(self.dirs.data / "products" / f"{rec['webcode']}.json", rec)

    def read(self, webcode=SONY65):
        return run.read_json(self.dirs.data / "products" / f"{webcode}.json")

    def test_sets_per_store_with_effective_accessory_price(self):
        self.write(product(offers=[offer(ONLINE_SHOP, 3469), offer(TAUENTZIEN, 3499, 4.3)]))
        self.write(product(PHILIPS, "e_977673", offers=[offer(ONLINE_SHOP, 2169)]))
        api, transport, _ = recorded_api(**{
            f"bundlesForArticle?articleId={SONY_ARTICLE}&storeId={ONLINE_SHOP}": [json_response(fixture("bundles-sony65-online"))],
            f"bundlesForArticle?articleId={SONY_ARTICLE}&storeId={TAUENTZIEN}": [json_response({"bundles": []})],
        })
        summary = sets.step(self.dirs.ctx(api, now=T0))
        self.assertEqual(summary, {"products": 1, "stores": 2, "sets": 1, "failed": 0, "skipped": []})
        rec = self.read()
        self.assertEqual(len(rec["sets"]), 1)
        s = rec["sets"][0]
        self.assertEqual((s["storeId"], s["productPrice"], s["accessoryEffective"], s["seen"]), (ONLINE_SHOP, 3469, 319, run.iso(T0)))
        self.assertEqual(rec["setsScan"], {"time": run.iso(T0), "stores": 2, "withSet": 1, "failed": 0})
        self.assertEqual(len([r for r in transport.requests if "bundlesForArticle" in r["url"]]), 2)  # Philips: watchSets false

    def test_failed_store_keeps_its_previous_sets(self):
        old = {"bundleId": "20000083", "storeId": TAUENTZIEN, "discount": 100, "promoted": 3788, "accessory": "Bar 6"}
        self.write(product(offers=[offer(ONLINE_SHOP, 3469), offer(TAUENTZIEN, 3499, 4.3)], sets_=[old]))
        api, _, _ = recorded_api(**{
            f"bundlesForArticle?articleId={SONY_ARTICLE}&storeId={ONLINE_SHOP}": [json_response({"bundles": []})],
            f"bundlesForArticle?articleId={SONY_ARTICLE}&storeId={TAUENTZIEN}": [json_response(SERVER_ERROR, 500)],
        })
        summary = sets.step(self.dirs.ctx(api, now=T0))
        self.assertEqual((summary["sets"], summary["failed"]), (1, 1))
        self.assertEqual(self.read()["sets"], [old])

    def test_product_without_scan_is_skipped(self):
        api, _, _ = recorded_api()
        summary = sets.step(self.dirs.ctx(api, now=T0))
        self.assertEqual(summary["skipped"], [SONY65, ])
        self.assertEqual(len(api.calls), 0)


class SetAlertTest(unittest.TestCase):
    STORES = {ONLINE_SHOP: {"id": ONLINE_SHOP, "name": "Online-Shop", "online": True, "distanceKm": None},
              RANGSDORF: {"id": RANGSDORF, "name": "ESC", "city": "Rangsdorf", "distanceKm": 24.7},
              "e_1907435": {"id": "e_1907435", "name": "expert Pasternak", "city": "Bochum", "distanceKm": 470}}

    def setUp(self):
        self.dirs = Dirs()
        self.addCleanup(self.dirs.cleanup)
        self.ntfy = FakeNtfy()

    def rules(self, rec, now=T0):
        inbox = alerts.Alerts(self.dirs.data, self.ntfy, now)
        inbox.set_rules(rec, self.STORES, 50)
        inbox.save()
        return inbox

    def deal(self, store_id, discount=100, bundle="20000083", distance=None):
        return {"bundleId": bundle, "storeId": store_id, "discount": discount, "promoted": 3788, "accessoryEffective": 319,
                "accessory": "Theatre Bar 6", "validTo": "30.11.2026", "distanceKm": distance}

    def test_new_set_online_and_in_range_once_per_bundle_and_store(self):
        rec = product(sets_=[self.deal(ONLINE_SHOP), self.deal(RANGSDORF, distance=24.7), self.deal("e_1907435", distance=470)])
        self.rules(rec)
        self.assertEqual(len(self.ntfy.sent), 2)  # Pasternak is out of range
        title, text, kw = self.ntfy.sent[0]
        self.assertEqual(title, "Set deal")
        self.assertEqual(text, 'Sony BRAVIA 9 II 65": set with Theatre Bar 6 −100 €, accessory effectively 319 € until 30.11.2026 · Online-Shop')
        self.assertEqual(kw["click"], f"https://www.expert.de/shop/{SONY65}-x.html?branch_id={ONLINE_SHOP}")
        self.assertEqual(self.ntfy.sent[1][1].endswith("· ESC Rangsdorf, 25 km"), True)
        self.rules(rec)
        self.assertEqual(len(self.ntfy.sent), 2)  # known now

    def test_discount_growth_of_20_euro_alerts_again_and_vanished_sets_reset(self):
        self.rules(product(sets_=[self.deal(ONLINE_SHOP, 100)]))
        self.rules(product(sets_=[self.deal(ONLINE_SHOP, 115)]))
        self.assertEqual(len(self.ntfy.sent), 1)
        self.rules(product(sets_=[self.deal(ONLINE_SHOP, 120)]))
        self.assertEqual(len(self.ntfy.sent), 2)
        self.rules(product(sets_=[]))
        self.assertEqual(run.read_json(self.dirs.data / "alerts.json")["state"]["sets"], {})
        self.rules(product(sets_=[self.deal(ONLINE_SHOP, 100)]))
        self.assertEqual(len(self.ntfy.sent), 3)


if __name__ == "__main__":
    unittest.main()
