import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scanner import alerts, run
from tests.test_run import FakeNtfy

T0 = datetime(2026, 11, 23, 13, 40, tzinfo=timezone.utc)
PHILIPS = "11128346052"
URL = "https://www.expert.de/shop/x/11128346052-65oled951-oled-tv.html"
RANGSDORF, ONLINE, TAUENTZIEN = "e_32472581", "e_2879130", "e_34627162"
STORES = {
    RANGSDORF: {"id": RANGSDORF, "name": "ESC", "city": "Rangsdorf", "distanceKm": 24.7},
    TAUENTZIEN: {"id": TAUENTZIEN, "name": "ESC", "city": "Berlin", "distanceKm": 4.3},
    "e_26051723": {"id": "e_26051723", "name": "expert Freital", "city": "Freital", "distanceKm": 168.1},
    ONLINE: {"id": ONLINE, "name": "Online-Shop", "city": None, "distanceKm": None},
}


def offer(store_id, price, shipped=None, pickup=None, display=None, unknown=False, distance=None):
    o = {"storeId": store_id, "price": price, "totalShipped": shipped, "totalPickup": pickup, "displayType": display,
         "distanceKm": distance}
    if unknown:
        o["unknown"] = True
    return o


def record(shipped=None, pickup=None, offers=(), history=(), incomplete=False, mode="every", target=None,
           scan_time=T0, unknown_best=False, label="Philips 65OLED951"):
    best = {"shipped": None, "pickup": None}
    if shipped is not None:
        best["shipped"] = {"storeId": ONLINE, "total": shipped, "distanceKm": None}
    if pickup is not None:
        best["pickup"] = {"storeId": RANGSDORF, "total": pickup, "distanceKm": 24.7}
        if unknown_best:
            best["pickup"]["unknown"] = True
    return {"webcode": PHILIPS, "label": label, "url": URL, "alertMode": mode, "targetPrice": target,
            "lastScan": run.iso(scan_time), "scan": {"incomplete": incomplete}, "best": best,
            "offers": list(offers), "history": list(history)}


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.ntfy = FakeNtfy()

    def inbox(self, now=T0):
        return alerts.Alerts(self.data, self.ntfy, now)

    def run_rules(self, rec, now=T0, min_drop=alerts.DEFAULT_MIN_DROP):
        inbox = self.inbox(now)
        inbox.product_rules(rec, STORES, min_drop)
        inbox.save()
        return inbox

    def file(self):
        return run.read_json(self.data / "alerts.json")

    # N1

    def test_first_scan_sets_the_baseline_without_an_alert(self):
        inbox = self.run_rules(record(shipped=2428.9, pickup=2095))
        self.assertEqual(inbox.raised, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS],
                         {"total": 2095, "path": "pickup", "storeId": RANGSDORF, "distanceKm": 24.7, "unknown": False,
                          "scan": "2026-11-23T13:40:00Z"})

    def test_drop_against_the_previous_scan(self):
        self.run_rules(record(shipped=2428.9, pickup=2095))
        inbox = self.run_rules(record(shipped=2428.9, pickup=2045, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(len(inbox.raised), 1)
        title, text, kw = self.ntfy.sent[-1]
        self.assertEqual(title, "Price drop")
        self.assertEqual(text, "Philips 65OLED951: 2 045 € pickup (was 2 095 €) · ESC Rangsdorf, 25 km")
        self.assertEqual(kw, {"click": f"{URL}?branch_id={RANGSDORF}", "tags": ["chart_with_downwards_trend"], "priority": None})
        item = self.file()["alerts"][-1]
        self.assertEqual((item["kind"], item["webcode"], item["storeId"], item["sent"]), ("price", PHILIPS, RANGSDORF, True))
        self.assertEqual(item["id"], f"2026-11-23T15:40:00Z:price:{PHILIPS}:{RANGSDORF}")
        self.assertEqual(self.file()["state"]["cooldowns"], {f"price:{PHILIPS}": "2026-11-23T15:40:00Z"})

    def test_shipped_path_when_it_is_the_lower_total(self):
        self.run_rules(record(shipped=2428.9, pickup=None))
        self.run_rules(record(shipped=2174.9, pickup=None, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.ntfy.sent[-1][1], "Philips 65OLED951: 2 174,90 € shipped (was 2 428,90 €) · Online-Shop")

    def test_rise_resets_the_baseline_so_a_drop_after_a_rise_counts(self):
        self.run_rules(record(pickup=2095))
        self.run_rules(record(pickup=2195, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.ntfy.sent, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS]["total"], 2195)
        self.run_rules(record(pickup=2150, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(self.ntfy.sent[-1][1], "Philips 65OLED951: 2 150 € pickup (was 2 195 €) · ESC Rangsdorf, 25 km")

    def test_cooldown_six_hours_keeps_the_swallowed_drop(self):
        self.run_rules(record(pickup=2095))
        self.run_rules(record(pickup=2045, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        inbox = self.run_rules(record(pickup=1995, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(inbox.raised, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS]["total"], 2045)  # baseline kept
        self.run_rules(record(pickup=1995, scan_time=T0 + timedelta(hours=8.5)), T0 + timedelta(hours=8.5))
        self.assertEqual(self.ntfy.sent[-1][1], "Philips 65OLED951: 1 995 € pickup (was 2 045 €) · ESC Rangsdorf, 25 km")

    def test_min_drop(self):
        self.run_rules(record(pickup=2095))
        self.run_rules(record(pickup=2094.5, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.ntfy.sent, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS]["total"], 2095)
        self.run_rules(record(pickup=2075, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4), min_drop=50)
        self.assertEqual(self.ntfy.sent, [])

    def test_incomplete_scan_and_unknown_best_are_skipped(self):
        self.run_rules(record(pickup=2095))
        self.run_rules(record(pickup=1995, incomplete=True, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.run_rules(record(pickup=1995, unknown_best=True, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(self.ntfy.sent, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS]["total"], 2095)

    def test_no_offer_at_all(self):
        inbox = self.run_rules(record())
        self.assertEqual(inbox.raised, [])
        self.assertNotIn(PHILIPS, self.file()["state"]["prices"])

    def test_low30_fires_only_below_the_earlier_days(self):
        history = [{"date": "2026-11-20", "shipped": 2300, "pickup": 2050}, {"date": "2026-11-23", "shipped": 2300, "pickup": 2095}]
        self.run_rules(record(pickup=2095, mode="low30", history=history))
        self.run_rules(record(pickup=2060, mode="low30", history=history, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.ntfy.sent, [])
        self.assertEqual(self.file()["state"]["prices"][PHILIPS]["total"], 2060)  # not a low, but the new baseline
        self.run_rules(record(pickup=2049, mode="low30", history=history, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(self.ntfy.sent[-1][1], "Philips 65OLED951: 2 049 € pickup (was 2 060 €) · ESC Rangsdorf, 25 km")

    def test_low30_ignores_days_older_than_30_days_and_today(self):
        old = [{"date": "2026-10-01", "shipped": None, "pickup": 1500}]
        self.assertIsNone(alerts.thirty_day_low(old, T0.date(), T0))
        today = [{"date": "2026-11-23", "shipped": None, "pickup": 1500}]
        self.assertIsNone(alerts.thirty_day_low(today, T0.date(), T0))
        self.assertEqual(alerts.thirty_day_low([{"date": "2026-10-25", "shipped": 1700, "pickup": 1600}], T0.date(), T0), 1600)

    def test_target_mode_leaves_drops_to_n2(self):
        self.run_rules(record(pickup=2095, mode="target", target=1500))
        self.run_rules(record(pickup=1995, mode="target", target=1500, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.ntfy.sent, [])

    # N2

    def test_target_fires_per_crossing(self):
        self.run_rules(record(pickup=2095, target=2000))
        self.assertEqual(self.ntfy.sent, [])
        self.run_rules(record(pickup=1999, target=2000, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        title, text, kw = self.ntfy.sent[-1]
        self.assertEqual((title, text), ("Target price reached", "Philips 65OLED951: 1 999 € pickup ≤ target 2 000 € · ESC Rangsdorf, 25 km"))
        self.assertEqual((kw["priority"], kw["tags"]), ("high", ["dart"]))
        self.assertEqual(self.file()["state"]["target"], {PHILIPS: "below"})
        self.run_rules(record(pickup=1990, target=2000, scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(len([s for s in self.ntfy.sent if s[0] == "Target price reached"]), 1)
        self.run_rules(record(pickup=2010, target=2000, scan_time=T0 + timedelta(hours=6)), T0 + timedelta(hours=6))
        self.assertEqual(self.file()["state"]["target"], {PHILIPS: "above"})
        self.run_rules(record(pickup=2000, target=2000, scan_time=T0 + timedelta(hours=8)), T0 + timedelta(hours=8))
        self.assertEqual(len([s for s in self.ntfy.sent if s[0] == "Target price reached"]), 2)

    def test_target_on_the_first_scan_and_removed_target(self):
        self.run_rules(record(pickup=1999, target=2000))
        self.assertEqual(self.ntfy.sent[-1][0], "Target price reached")
        self.run_rules(record(pickup=1999, target=None, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(self.file()["state"]["target"], {})

    # N3

    def test_display_deal_15_percent_below_the_best_regular_offer(self):
        offers = [offer(ONLINE, 2500, shipped=2579.9), offer(RANGSDORF, 2095, shipped=2174.9, pickup=2095, display="Aussteller", distance=24.7)]
        self.run_rules(record(shipped=2174.9, pickup=2095, offers=offers))
        title, text, kw = self.ntfy.sent[-1]
        self.assertEqual((title, text), ("Restposten deal", "Philips 65OLED951: 2 095 € Aussteller pickup, 19 % below 2 579,90 € · ESC Rangsdorf, 25 km"))
        self.assertEqual(kw["click"], f"{URL}?branch_id={RANGSDORF}")
        self.assertEqual(self.file()["state"]["restposten"], {f"{PHILIPS}:{RANGSDORF}": "2026-11-23T13:40:00Z"})
        self.run_rules(record(shipped=2174.9, pickup=2095, offers=offers, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual(len(self.ntfy.sent), 1)  # once per store and product

    def test_display_deal_not_far_enough_below(self):
        offers = [offer(ONLINE, 2359, shipped=2428.9), offer(RANGSDORF, 2095, pickup=2095, display="Aussteller", distance=24.7)]
        self.run_rules(record(shipped=2428.9, pickup=2095, offers=offers))
        self.assertEqual(self.ntfy.sent, [])

    def test_display_deal_outside_the_radius_or_without_regular_offer(self):
        far = [offer(ONLINE, 2500, shipped=2579.9), offer("e_26051723", 1500, pickup=None, display="Restposten", distance=168.1)]
        self.run_rules(record(shipped=2579.9, offers=far))
        only_display = [offer(RANGSDORF, 1500, pickup=1500, display="Restposten", distance=24.7)]
        self.run_rules(record(pickup=1500, offers=only_display, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertEqual([s for s in self.ntfy.sent if s[0] == "Restposten deal"], [])

    def test_display_deal_fires_again_after_it_vanished(self):
        offers = [offer(ONLINE, 2500, shipped=2579.9), offer(RANGSDORF, 2095, pickup=2095, display="Restposten", distance=24.7)]
        self.run_rules(record(shipped=2579.9, pickup=2095, offers=offers))
        kept = [offers[0], {**offers[1], "unknown": True}]
        self.run_rules(record(shipped=2579.9, pickup=2095, offers=kept, scan_time=T0 + timedelta(hours=2)), T0 + timedelta(hours=2))
        self.assertIn(f"{PHILIPS}:{RANGSDORF}", self.file()["state"]["restposten"])  # kept-unknown offers do not reset
        self.run_rules(record(shipped=2579.9, offers=offers[:1], scan_time=T0 + timedelta(hours=4)), T0 + timedelta(hours=4))
        self.assertEqual(self.file()["state"]["restposten"], {})
        self.run_rules(record(shipped=2579.9, pickup=2095, offers=offers, scan_time=T0 + timedelta(hours=6)), T0 + timedelta(hours=6))
        self.assertEqual(len([s for s in self.ntfy.sent if s[0] == "Restposten deal"]), 2)

    # N7

    def test_failure_for_aborted_run_and_failed_step_with_cooldown(self):
        status = {"aborted": "prices: ChallengeError: cf-mitigated", "steps": {
            "stores": {"lastAttempt": run.iso(T0), "ok": False, "error": "store count changed from 348 to 200"},
            "cashback": {"lastAttempt": run.iso(T0 - timedelta(hours=2)), "ok": False, "error": "old"}}}
        inbox = self.inbox()
        inbox.failure_rules(status)
        inbox.save()
        title, text, kw = self.ntfy.sent[-1]
        self.assertEqual(title, "expert-checker: scan failed")
        self.assertEqual(text, "run aborted: prices: ChallengeError: cf-mitigated; stores failed: store count changed from 348 to 200")
        self.assertEqual((kw["priority"], kw["tags"]), ("high", ["rotating_light"]))
        self.assertEqual(inbox.raised, ["2026-11-23T13:40:00Z:failure:failure:run"])
        later = self.inbox(T0 + timedelta(hours=2))
        later.failure_rules({"aborted": "again", "steps": {}})
        self.assertEqual(later.raised, [])
        self.assertEqual(len(self.ntfy.sent), 1)
        self.inbox(T0 + timedelta(hours=2)).failure_rules({"aborted": None, "steps": {}})
        self.assertEqual(len(self.ntfy.sent), 1)

    # File and sending

    def test_inbox_keeps_the_last_200(self):
        inbox = self.inbox()
        inbox.items = [{"id": str(i)} for i in range(205)]
        inbox.emit("failure", None, "x")
        inbox.save()
        items = self.file()["alerts"]
        self.assertEqual(len(items), 200)
        self.assertEqual(items[-1]["text"], "x")
        self.assertEqual(items[0]["id"], "6")

    def test_failed_send_is_a_warning_and_the_alert_stays_in_the_file(self):
        class Down:
            enabled = True
            def send(self, *a, **k):
                return False
            def last_error(self):
                return "ntfy: 503"
        inbox = alerts.Alerts(self.data, Down(), T0)
        self.assertTrue(inbox.emit("price", None, "x", webcode=PHILIPS))
        inbox.save()
        self.assertEqual(inbox.warnings, ["ntfy failed: ntfy: 503"])
        self.assertFalse(self.file()["alerts"][-1]["sent"])

    def test_no_topic_is_no_warning(self):
        class Off:
            enabled = False
            def send(self, *a, **k):
                return False
        inbox = alerts.Alerts(self.data, Off(), T0)
        inbox.emit("price", None, "x")
        self.assertEqual(inbox.warnings, [])

    def test_old_cooldowns_are_pruned(self):
        inbox = self.inbox()
        inbox.state["cooldowns"] = {"price:a": run.iso(T0 - timedelta(days=8)), "price:b": run.iso(T0 - timedelta(days=6))}
        inbox.save()
        self.assertEqual(list(self.file()["state"]["cooldowns"]), ["price:b"])


class HelpersTest(unittest.TestCase):
    def test_fmt_price(self):
        self.assertEqual(alerts.fmt_price(2095), "2 095 €")
        self.assertEqual(alerts.fmt_price(2174.9), "2 174,90 €")
        self.assertEqual(alerts.fmt_price(72.99), "72,99 €")
        self.assertEqual(alerts.fmt_price(999.999), "1 000 €")
        self.assertEqual(alerts.fmt_price(None), "–")

    def test_store_text(self):
        self.assertEqual(alerts.store_text(STORES[RANGSDORF], 24.7), "ESC Rangsdorf, 25 km")
        self.assertEqual(alerts.store_text(STORES["e_26051723"], 168.1), "expert Freital, 168 km")
        self.assertEqual(alerts.store_text(STORES[ONLINE], None), "Online-Shop")
        self.assertEqual(alerts.store_text(None, 3), "unknown store")

    def test_effective_prefers_the_lower_total(self):
        self.assertEqual(alerts.effective(record(shipped=2000, pickup=2095))["path"], "shipped")
        self.assertEqual(alerts.effective(record(shipped=2100, pickup=2095))["path"], "pickup")
        self.assertIsNone(alerts.effective(record()))
        self.assertIsNone(alerts.effective({}))


if __name__ == "__main__":
    unittest.main()
