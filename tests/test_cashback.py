import unittest
from datetime import datetime, timezone
from pathlib import Path

from scanner import alerts, cashback, run
from scanner.expert_api import ONLINE_SHOP
from tests.recorded import FIXTURES, PHILIPS, SONY65, fixture, recorded_api
from tests.test_expert_api import json_response
from tests.test_run import FakeNtfy
from tests.test_stores import Dirs

T0 = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
SONY8 = "e_944796"      # K-65XR8M25B BRAVIA 8 II, in the Sony cashback
FRAME65 = "e_973320"    # GQ65LS03HWUXZG The Frame Pro, in the Samsung cashback


def pdf_text(url):
    name = "e_4294" if "Double-Cashback" in url else "e_4288"
    return (FIXTURES / f"pdf-{name}.txt").read_text()


def product(webcode, article_id, brand, name):
    return {"webcode": webcode, "label": name, "articleId": article_id, "brand": brand, "name": name,
            "url": f"https://www.expert.de/shop/{webcode}-x.html", "lastScan": run.iso(T0),
            "best": {"shipped": {"storeId": ONLINE_SHOP, "total": 2159}, "pickup": {"storeId": "e_32472581", "total": 2095, "distanceKm": 24.7}},
            "offers": [], "history": [], "sets": []}


class ClassifyTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(cashback.classify("Sony Cashback"), "cashback")
        self.assertEqual(cashback.classify("Bis zu 100 € Cashback!"), "cashback")
        self.assertEqual(cashback.classify("Assassin's Creed sichern!"), "extra")
        self.assertEqual(cashback.classify("100 Tage testen"), "extra")
        self.assertEqual(cashback.classify("100 Tage Geld-zurück-Garantie"), "extra")
        self.assertEqual(cashback.classify("+1 Jahr Garantieverlängerung"), "extra")
        self.assertEqual(cashback.classify("Inklusive Streaming Content*"), "extra")
        self.assertEqual(cashback.classify("PayPal 0 % Finanzierung"), "other")
        self.assertEqual(cashback.classify("8FACH PAYBACK °Punkte"), "other")
        self.assertEqual(cashback.classify("10€ Rabatt mit WERO10"), "other")
        self.assertEqual(cashback.classify("Samsung Black Weeks"), "other")
        self.assertEqual(cashback.classify("Kostenlose Altgerätemitnahme"), "other")

    def test_brand_in_text(self):
        brands = {"philips", "sony", "lg", "samsung"}
        self.assertEqual(cashback.brand_in_text("Jetzt Philips Ambilight TV kaufen", brands), "Philips")
        self.assertEqual(cashback.brand_in_text("Sony Cashback", brands), "Sony")
        self.assertIsNone(cashback.brand_in_text("Neff Cashback für Backöfen", brands))
        self.assertIsNone(cashback.brand_in_text("Lgbt", brands))


class DatesTest(unittest.TestCase):
    def test_sony(self):
        d = cashback.parse_dates("Kaufe im Aktionszeitraum vom 12.11. – 10.01.2027 eines der Modelle. Fülle das Antragsformular "
                                 "aus und registriere dort Dein Gerät vom 10.12. – 07.03.2027.")
        self.assertEqual(d, {"buyFrom": "2026-11-12", "buyTo": "2027-01-10", "registerFrom": "2026-12-10", "registerBy": "2027-03-07"})

    def test_samsung_and_philips(self):
        d = cashback.parse_dates("Kaufe zwischen dem 16.11. – 06.12.2026 ein Gerät. Registriere Dich bis zum 20.12.2026 unter x")
        self.assertEqual(d, {"buyFrom": "2026-11-16", "buyTo": "2026-12-06", "registerFrom": None, "registerBy": "2026-12-20"})
        d = cashback.parse_dates("Kaufe zwischen dem 01.10. und 31.12.2026 ein Gerät. Registriere Dich frühestens 30 Tage nach "
                                 "dem Kaufdatum bis spätestens zum 14.02.2027 unter x")
        self.assertEqual((d["buyFrom"], d["buyTo"], d["registerBy"]), ("2026-10-01", "2026-12-31", "2027-02-14"))
        d = cashback.parse_dates("Kaufe bis zum 31.03.2027 ein teilnehmendes Aktionsgerät.")
        self.assertEqual((d["buyFrom"], d["buyTo"], d["registerBy"]), (None, "2027-03-31", None))

    def test_year_of_the_first_date(self):
        self.assertEqual(cashback.iso_date("12.11.", "2027-01-10"), "2026-11-12")
        self.assertEqual(cashback.iso_date("05.01.", "2027-01-10"), "2027-01-05")
        self.assertIsNone(cashback.iso_date("31.02.2027"))


class PdfTest(unittest.TestCase):
    def test_sony_layout(self):
        parsed = cashback.parse_pdf_text(pdf_text("FY26_HE_Double-Cashback_Promo_Expert_BG-AT.pdf"))
        self.assertEqual((parsed["layout"], parsed["sameInvoice"], len(parsed["tvs"]), len(parsed["bars"])), ("sony", True, 8, 6))
        self.assertEqual(parsed["tvs"][7], {"modelCode": "K-65XR8M2", "sap": "K65XR8M25B", "label": '65" BRAVIA 8 II', "inch": 65,
                                            "amount": 250, "amountDouble": 500})
        self.assertEqual([b["modelCode"] for b in parsed["bars"]], ["HT-A7100", "HT-A7100KIT", "HT-A9000", "HT-A9M2", "HT-A8", "HT-A8KIT"])
        self.assertEqual(parsed["bars"][3]["label"], "Theatre Quad")

    def test_samsung_layout(self):
        parsed = cashback.parse_pdf_text(pdf_text("SEG_VSX_The_Frame_Pro_Deals_TNBs.pdf"))
        self.assertEqual((parsed["layout"], parsed["sameInvoice"]), ("samsung", False))
        self.assertEqual([(t["modelCode"], t["amount"]) for t in parsed["tvs"]],
                         [("GQ85LS03HWUXZG", 250), ("GQ75LS03HWUXZG", 200), ("GQ65LS03HWUXZG", 150), ("GQ55LS03HWUXZG", 130)])

    def test_unknown_layout(self):
        self.assertEqual(cashback.parse_pdf_text("Teilnahmebedingungen ohne Tabelle")["layout"], "unknown")

    def test_match_tv(self):
        tvs = cashback.parse_pdf_text(pdf_text("Double-Cashback"))["tvs"]
        self.assertEqual(cashback.match_tv("K-65XR8M25B BRAVIA 8 II OLED TV", tvs)["amount"], 250)
        self.assertEqual(cashback.match_tv("K55XR79M2B BRAVIA 7 II True RGB TV", tvs)["amount"], 175)
        self.assertIsNone(cashback.match_tv("K65XR95M2PB BRAVIA 9 II True RGB TV", tvs))


class StepTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs(products=({"webcode": PHILIPS, "label": "Philips 65OLED951"}, {"webcode": SONY65, "label": "Sony 65"}))
        run.write_json(self.dirs.config / "watchlist.json", {"location": {"zip": "14167", "lat": 52.5167, "lng": 13.4, "maxDistanceKm": 50},
                                                            "brands": ["Philips", "Sony", "Samsung"],
                                                            "products": [{"webcode": PHILIPS}, {"webcode": SONY65}]})
        self.addCleanup(self.dirs.cleanup)
        self.write(product(PHILIPS, "e_977673", "Philips", "65OLED951 OLED TV"))
        self.write(product(SONY65, "e_973660", "Sony", "K65XR95M2PB BRAVIA 9 II True RGB TV"))
        self.old_pdf = cashback.PDF_TEXT
        cashback.PDF_TEXT = pdf_text
        self.addCleanup(setattr, cashback, "PDF_TEXT", self.old_pdf)

    def write(self, rec):
        run.write_json(self.dirs.data / "products" / f"{rec['webcode']}.json", rec)

    def api(self):
        return recorded_api(**{
            "promotions/getIndex": [json_response(fixture("getIndex-online"))],
            f"search/article?articleId={SONY8}": [json_response(fixture(f"article-{SONY8}"))],
            f"search/article?articleId={FRAME65}": [json_response(fixture(f"article-{FRAME65}"))],
            "pricepds?webcode=11128360730": [json_response(fixture("pricepds-sony65-online"))],
            "pricepds?webcode=11128962771": [json_response(fixture("pricepds-philips-online"))],
        })

    def run_step(self, now=T0):
        api, transport, _ = self.api()
        summary = cashback.step(self.dirs.ctx(api, now=now))
        return summary, run.read_json(self.dirs.data / "cashbacks.json"), transport

    def test_relevant_promotions_kinds_and_dates(self):
        summary, data, _ = self.run_step()
        self.assertEqual(sorted(data["promotions"]), ["e_3157", "e_3693", "e_4066", "e_4203", "e_4288", "e_4294"])
        self.assertEqual((summary["cashbacks"], summary["extras"], summary["kept"]), (2, 3, 6))
        sony = data["promotions"]["e_4294"]
        self.assertEqual((sony["kind"], sony["brand"], sony["buyFrom"], sony["buyTo"], sony["registerBy"], sony["sameInvoice"]),
                         ("cashback", "Sony", "2026-11-12", "2027-01-10", "2027-03-07", True))
        self.assertEqual(sony["url"], "https://www.sony.de/cashback/TVWinter2026")
        self.assertEqual((sony["amountSource"], sony["pdfLayout"], len(sony["devices"]), len(sony["soundbars"])), ("pdf", "sony", 8, 6))
        philips = data["promotions"]["e_4203"]
        self.assertEqual((philips["kind"], philips["brand"], philips["watched"], philips["buyTo"], philips["registerBy"]),
                         ("extra", "Philips", [PHILIPS], "2026-12-31", "2027-02-14"))
        paypal = data["promotions"]["e_3157"]
        self.assertEqual((paypal["kind"], paypal["brand"], sorted(paypal["watched"])), ("other", None, [PHILIPS, SONY65]))  # kept: touches watched products
        self.assertNotIn("articleIds", paypal)
        self.assertEqual(paypal["articleCount"], 3)
        samsung = data["promotions"]["e_4288"]
        self.assertEqual(samsung["url"], "https://samsung.de/theframeprodeals")
        self.assertEqual(data["updated"], run.iso(T0))

    def test_devices_with_amounts_and_online_prices(self):
        summary, data, _ = self.run_step()
        sony = data["promotions"]["e_4294"]
        d = next(x for x in sony["devices"] if x["articleId"] == SONY8)
        self.assertEqual((d["webcode"], d["name"], d["type"], d["amount"], d["amountDouble"], d["source"], d["watched"]),
                         ("11128360730", "K-65XR8M25B BRAVIA 8 II OLED TV", "tv", 250, 500, "pdf", False))
        self.assertEqual((d["price"], d["priceSource"]), (3459, "online"))  # recorded Sony online offer: 3469 − 10 € code
        unresolved = [x for x in sony["devices"] if x["name"] is None]
        self.assertEqual(len(unresolved), 7)  # the recorded API knows one Sony article; the rest stay index-only
        bar = next(b for b in sony["soundbars"] if b["modelCode"] == "HT-A7100KIT")
        self.assertEqual(bar["webcode"], "12220065730")  # named in the Sony set-deal description
        self.assertIsNone(next(b for b in sony["soundbars"] if b["modelCode"] == "HT-A7100")["webcode"])
        frame = next(x for x in data["promotions"]["e_4288"]["devices"] if x["articleId"] == FRAME65)
        self.assertEqual((frame["amount"], frame["modelCode"], frame["price"]), (150, "GQ65LS03HWUXZG", 2428.9))
        self.assertEqual(summary["articleLookups"], 13)  # 8 Sony + 4 Samsung articles + 1 soundbar by webcode
        self.assertTrue((self.dirs.data / "articles.json").exists())

    def test_product_files_get_promotion_ids_and_a_cashback_block(self):
        self.run_step()
        philips = run.read_json(self.dirs.data / "products" / f"{PHILIPS}.json")
        self.assertEqual(philips["promotionIds"], ["e_3157", "e_4066", "e_4203"])
        self.assertIsNone(philips["cashback"])
        sony = run.read_json(self.dirs.data / "products" / f"{SONY65}.json")
        self.assertEqual(sony["promotionIds"], ["e_3157", "e_4205", "e_4206"])
        self.assertIsNone(sony["cashback"])  # the BRAVIA 9 II is not in the Sony cashback

    def test_cashback_block_for_a_qualifying_watched_product(self):
        self.write(product("11128360730", SONY8, "Sony", "K-65XR8M25B BRAVIA 8 II OLED TV"))
        run.write_json(self.dirs.config / "watchlist.json", {"brands": ["Sony"], "products": [{"webcode": "11128360730"}]})
        self.run_step()
        rec = run.read_json(self.dirs.data / "products" / "11128360730.json")
        block = rec["cashback"]
        self.assertEqual((block["promotionId"], block["amount"], block["amountDouble"], block["buyTo"], block["sameInvoice"]),
                         ("e_4294", 250, 500, "2027-01-10", True))
        self.assertEqual(alerts.effective(rec), {"total": 1845, "path": "pickup", "storeId": "e_32472581", "distanceKm": 24.7,
                                                "unknown": False, "cashback": 250})
        d = next(x for x in run.read_json(self.dirs.data / "cashbacks.json")["promotions"]["e_4294"]["devices"] if x["articleId"] == SONY8)
        self.assertEqual((d["watched"], d["price"], d["priceSource"]), (True, 2095, "watchlist"))

    def test_second_run_uses_the_caches_and_keeps_ended_promotions(self):
        self.run_step()
        api, transport, _ = self.api()
        index = fixture("getIndex-online")
        del index["globalPromotions"]["e_4288"]
        transport.scripts["promotions/getIndex"] = [json_response(index)]
        cashback.PDF_TEXT = lambda url: (_ for _ in ()).throw(AssertionError("PDF parsed again"))
        summary = cashback.step(self.dirs.ctx(api, now=T0))
        self.assertEqual((summary["articleLookups"], summary["priceLookups"]), (8, 2))  # 7 unresolved articles and the soundbar retried; 1 TV + 1 soundbar priced
        data = run.read_json(self.dirs.data / "cashbacks.json")
        self.assertFalse(data["promotions"]["e_4288"]["active"])
        self.assertTrue(data["promotions"]["e_4294"]["active"])
        self.assertEqual(data["promotions"]["e_4294"]["firstSeen"], run.iso(T0))

    def test_override_fills_amounts_and_adds_devices(self):
        run.write_json(self.dirs.config / "cashback-overrides.json", {
            "e_4288": {"sameInvoice": False, "devices": [{"modelCode": "GQ65LS03HWUXZG", "amount": 160},
                                                         {"modelCode": "HW-Q990F", "type": "soundbar", "name": "Samsung HW-Q990F"}]}})
        _, data, _ = self.run_step()
        samsung = data["promotions"]["e_4288"]
        frame = next(x for x in samsung["devices"] if x["articleId"] == FRAME65)
        self.assertEqual((frame["amount"], frame["source"], samsung["amountSource"]), (160, "override", "override"))
        self.assertEqual(samsung["soundbars"][0]["name"], "Samsung HW-Q990F")

    def test_without_pypdf_amounts_stay_unknown_with_a_warning(self):
        cashback.PDF_TEXT = lambda url: (_ for _ in ()).throw(cashback.MissingPdfLibrary("pypdf is not installed"))
        summary, data, _ = self.run_step()
        self.assertEqual(data["promotions"]["e_4294"]["amountSource"], "unknown")
        self.assertIn("pypdf is not installed: cashback amounts stay unknown", summary["warnings"])


class CashbackAlertTest(unittest.TestCase):
    def setUp(self):
        self.dirs = Dirs()
        self.addCleanup(self.dirs.cleanup)
        self.ntfy = FakeNtfy()

    def rules(self, promotions, now=T0):
        inbox = alerts.Alerts(self.dirs.data, self.ntfy, now)
        inbox.cashback_rules({"updated": run.iso(now), "promotions": promotions})
        inbox.save()
        return inbox

    def sony(self, source="pdf", buy_to="2027-01-10", active=True):
        devices = [{"amount": 150, "amountDouble": 300}, {"amount": 250, "amountDouble": 500}] if source != "unknown" else [{"amount": None}]
        return {"id": "e_4294", "kind": "cashback", "title": "Sony Cashback", "brand": "Sony", "buyTo": buy_to, "registerBy": "2027-03-07",
                "url": "https://www.sony.de/cashback/TVWinter2026", "amountSource": source, "devices": devices, "watched": [], "active": active}

    def test_new_with_amounts_is_one_message(self):
        self.rules({"e_4294": self.sony()})
        self.assertEqual(len(self.ntfy.sent), 1)
        title, text, kw = self.ntfy.sent[0]
        self.assertEqual(title, "New cashback")
        self.assertEqual(text, "New cashback: Sony Cashback (Sony): 150–250 €, up to 500 € with soundbar, buy until 2027-01-10, register by 2027-03-07")
        self.assertEqual(kw["click"], "https://www.sony.de/cashback/TVWinter2026")
        self.rules({"e_4294": self.sony()})
        self.assertEqual(len(self.ntfy.sent), 1)

    def test_amounts_known_later_and_ending_soon(self):
        self.rules({"e_4294": self.sony(source="unknown")})
        self.assertIn("amount unknown", self.ntfy.sent[0][1])
        self.rules({"e_4294": self.sony()})
        self.assertEqual(self.ntfy.sent[1][0], "Cashback amounts known")
        self.rules({"e_4294": self.sony(buy_to="2026-11-26")}, now=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(self.ntfy.sent[2][0], "Cashback ends soon")
        self.assertTrue(self.ntfy.sent[2][1].startswith("Ends in 2 days: Sony Cashback"))
        self.assertEqual(self.ntfy.sent[2][2]["priority"], "high")
        self.rules({"e_4294": self.sony(buy_to="2026-11-26")}, now=datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(len(self.ntfy.sent), 3)

    def test_other_and_ended_promotions_are_silent_and_state_is_pruned(self):
        self.rules({"e_3157": {**self.sony(), "id": "e_3157", "kind": "other"}, "e_4288": self.sony(active=False)})
        self.assertEqual(self.ntfy.sent, [])
        self.rules({"e_4294": self.sony()})
        self.rules({})
        self.assertEqual(run.read_json(self.dirs.data / "alerts.json")["state"]["cashback"], {})


if __name__ == "__main__":
    unittest.main()
